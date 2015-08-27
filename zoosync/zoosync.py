#! /usr/bin/python

import logging
import getopt
import os
import pkg_resources
import re
import socket
import sys
import subprocess
import random
import threading
import time
import Queue
from kazoo.client import KazooClient
from kazoo.security import make_digest_acl, make_acl

import version

N_PING_THREADS = 4

MULTI_FIRST = 1
MULTI_RANDOM = 2
MULTI_LIST = 3

zookeeper_hosts = 'localhost:2181'
base = '/indigo-testbed'
dry = False
multi = MULTI_FIRST
user = 'indigo-testbed'
password = 'changeit'
services = []
admin_acl = 'world:anyone:r'

hostname = socket.getfqdn()
poll_interval=10
wait_time = 1800
zk = None
adminAcls = []
hiddenAcls = []
myAcl = None

output = {}
summary = {}

q_active = Queue.Queue()
q_inactive = Queue.Queue()


def usage():
	print 'Usage: %s [OPTIONS] commands\n\
OPTIONS:\n\
  -h, --help ......... usage message\n\
  -a, --acl .......... additional ACL\n\
  -b, --base ......... base zookeeper directory\n\
  -n, --dry .......... read-only network operations\n\
  -H, --hostname ..... use specified hostname\n\
  -m, --multi ........ selection from multiple endpoints\n\
  -u, --user ......... user\n\
  -w, --wait ......... time to wait for wait command\n\
  -p, --password ..... password\n\
  -s, --services ..... comma separated list of services\n\
  -z, --zookeeper .... comma separated list of zookeeper hosts\n\
COMMANDS:\n\
  list ....... get all services\n\
  get ........ get given services\n\
  cleanup .... get given services (only active), remove inactive\n\
  create ..... create a service\n\
  purge ...... purge all endpoints of the service\n\
  read-tag ... read specifig tag\n\
  read-tags .. read all tags\n\
  register ... register a service\n\
  remove ..... remove given services\n\
  tag ........ create a tag\n\
  tags ....... read all tags\n\
  unregister . unregister services\n\
  untag ...... remove a tag\n\
  wait ....... wait for given services\n\
' % sys.argv[0]


def service2env(s):
	return re.sub(r'[\.-]', r'_', s.upper())


def str2acl(s, hidden = False):
	create = False
	delete = False
	read = False
	write = False
	admin = False

	if re.match('.+:.+:.+', s):
		permissions = re.sub(r'(.*):([^:]*)', r'\2', s)
		s = re.sub(r'(.*):([^:]*)', r'\1', s)
		scheme, credential = re.split(':', s, 1)

		if re.search('c', permissions):
			create = True
		if re.search('d', permissions):
			delete = True
		if re.search('r', permissions) and not hidden:
			read = True
		if re.search('w', permissions):
			write = True
		if re.search('a', permissions) and not hidden:
			admin = True
		if create or delete or read or write or admin:
			return make_acl(scheme, credential, create = create, delete = delete, read = read, write = write, admin = admin)
		else:
			return None
	else:
		print >> sys.stderr, 'Warning: invalid ACL: %s' % s
		return None


#
# threaded pinger
#
# http://stackoverflow.com/questions/316866/ping-a-site-in-python
def pinger(i, q):
	while True:
		ip, services = q.get()
		#print "[thread %s] pinging %s" % (i, ip)
		ret = subprocess.call("ping6 -c 1 -W 2 %s" % ip,
			shell = True,
			stdout = open('/dev/null', 'w'),
			stderr = subprocess.STDOUT)
		if ret != 0:
			ret = subprocess.call("ping -c 1 -W 2 %s" % ip,
				shell = True,
				stdout = open('/dev/null', 'w'),
				stderr = subprocess.STDOUT)
		if ret == 0:
			#print '%s active' % ip
			q_active.put([ip, services])
		else:
			#print '%s dead' % ip
			q_inactive.put([ip, services])
		q.task_done()


def zoo_create(path, strict):
	if not dry:
		if strict:
			zk.retry(zk.create, path, value = '', acl = adminAcls + [myAcl])
		else:
			zk.retry(zk.ensure_path, path, adminAcls + [myAcl])


def zoo_hostnames(path, multi, deleted = False):
	children = []

	for child in sorted(zk.retry(zk.get_children, path)):
		if deleted or not zk.exists('%s/%s/.deleted' % (path, child)):
			children.append(child)

	if not children:
		return []
	if multi == MULTI_FIRST:
		return [children[0]]
	elif multi == MULTI_RANDOM:
		index = random.randrange(0, len(children))
		return [children[index]]
	else:
		return children


def cleanup():
	global summary, output

	service_hostnames = {}
	queue = Queue.Queue()

	get(MULTI_LIST)

	all_services = {}
	for s in summary['SERVICES']:
		name = service2env(s)
		hostnames = output['SERVICE_%s' % name]
		for ip in hostnames:
			if not ip in service_hostnames:
				service_hostnames[ip] = []
			service_hostnames[ip].append(s)
			all_services[s] = True
	for s in summary['MISSING']:
			all_services[s] = True

	for i in range(N_PING_THREADS):
		worker = threading.Thread(target=pinger, args=(i, queue))
		worker.setDaemon(True)
		worker.start()

	for ip, hostnames in service_hostnames.items():
		queue.put([ip, hostnames])
	queue.join()

	# cleanups
	removed_services = {}
	while not q_inactive.empty():
		ip, inactive_services = q_inactive.get()
		for s in inactive_services:
			path = '%s/%s/%s' % (base, s, ip)
			name = service2env(s)

			if not dry:
				zk.retry(zk.delete, path, recursive = True)

			if not s in removed_services:
				removed_services[s] = []
			removed_services[s].append(ip)

		q_inactive.task_done()

	# remains active
	summary_services = {}
	while not q_active.empty():
		ip, active_services = q_active.get()
		for s in active_services:
			name = service2env(s)
			if not s in summary_services:
				summary_services[s] = []
			summary_services[s].append(ip)
		q_active.task_done()

	# required services and not active are missing
	missing_services = {}
	for s in sorted(all_services.keys()):
		if not s in summary_services:
			missing_services[s] = True

	summary = {}
	output = {}
	summary['REMOVED'] = sorted(removed_services.keys())
	for s, hostnames in sorted(removed_services.items()):
		output['REMOVED_%s' % s] = sorted(hostnames)
	summary['MISSING'] = sorted(missing_services.keys())
	summary['SERVICES'] = sorted(summary_services.keys())
	for s, hostnames in sorted(summary_services.items()):
		output['SERVICE_%s' % s] = sorted(hostnames)


def get(multi):
	global summary, output

	if not services:
		return
	if 'SERVICES' not in summary:
		summary['SERVICES'] = []
	if 'MISSING' not in summary:
		summary['MISSING'] = []

	for s in services:
		path = '%s/%s' % (base, s)
		name = service2env(s)
		values = []
		if zk.exists(path):
			values = zoo_hostnames(path, multi)
		if values:
			summary['SERVICES'].append(s)
		else:
			summary['MISSING'].append(s)
		output['SERVICE_%s' % name] = values


def list():
	if 'SERVICES' not in summary:
		summary['SERVICES'] = []

	children = zk.retry(zk.get_children, base)
	for s in sorted(children):
		path = '%s/%s' % (base, s)
		name = service2env(s)
		values = zoo_hostnames(path, multi)
		if values:
			summary['SERVICES'].append(s)
		output['SERVICE_%s' % name] = values


def create(strict = True):
	if not services:
		return
	if 'SERVICES' not in summary:
		summary['SERVICES'] = []

	for s in services:
		parent_path = '%s/%s' % (base, s)
		path = '%s/%s' % (parent_path, hostname)
		name = service2env(s)
		values = [hostname]
		zoo_create(parent_path, strict = False)
		if zk.exists('%s/.deleted' % path):
			if not dry:
				zk.retry(zk.delete, '%s/.deleted' % path)
		else:
			zoo_create(path, strict)

		summary['SERVICES'].append(s)
		output['SERVICE_%s' % name] = values


def remove():
	if not services:
		return
	if 'REMOVED' not in summary:
		summary['REMOVED'] = []

	for s in services:
		path = '%s/%s/%s' % (base, s, hostname)
		name = service2env(s)
		values = [hostname]
		if zk.exists(path):
			if not dry:
				zk.retry(zk.delete, path, recursive = True)
			summary['REMOVED'].append(s)
			output['REMOVED_%s' % name] = values
		else:
			raise ValueError('service endpoint %s/%s doesn\'t exist' % (s, hostname))


def unregister():
	if not services:
		return
	if 'REMOVED' not in summary:
		summary['REMOVED'] = []

	for s in services:
		path = '%s/%s/%s' % (base, s, hostname)
		name = service2env(s)
		values = [hostname]
		if zk.exists(path) and not zk.exists('%s/.deleted' % path):
			zoo_create('%s/.deleted' % path, strict = False)
			summary['REMOVED'].append(s)
			output['REMOVED_%s' % name] = values


def wait():
	if not services:
		return
	if wait_time > 0:
		count = wait_time / poll_interval
	else:
		count = 1

	ok=False
	while not ok and count > 0:
		ok=True
		if wait_time > 0:
			count -= 1
		for s in services:
			path = '%s/%s' % (base, s)
			values = None
			if zk.exists(path):
				values = zoo_hostnames(path, multi)
			if not values:
				ok=False
				time.sleep(poll_interval)
				break
	get(multi)
	if not summary['MISSING']:
		del summary['MISSING']


def purge():
	if not services:
		return
	if 'REMOVED' not in summary:
		summary['REMOVED'] = []

	for s in services:
		path = '%s/%s' % (base, s)
		name = service2env(s)
		if zk.exists(path):
			values = zoo_hostnames(path, MULTI_LIST, deleted = True)
			if not dry:
				zk.retry(zk.delete, path, recursive = True)
			summary['REMOVED'].append(s)
			output['REMOVED_%s' % name] = values


def tag(tagname, tagvalue):
	if not services:
		return
	if 'MODIFIED' not in summary:
		summary['MODIFIED'] = []

	if re.match(r'_', tagname):
		acls = hiddenAcls
	else:
		acls = adminAcls
	for s in services:
		path = '%s/%s/%s/%s' % (base, s, hostname, tagname)
		name = service2env(s)
		if not dry:
			zk.retry(zk.create, path, value = tagvalue, acl = acls + [myAcl])
		summary['MODIFIED'].append(s)
		output['MODIFIED_%s' % name] = [hostname]


def readtag(tagname):
	if 'SERVICES' not in summary:
		summary['SERVICES'] = []

	for s in services:
		path = '%s/%s/%s/%s' % (base, s, hostname, tagname)
		name = service2env(s)
		if zk.exists(path):
			value = zk.retry(zk.get, path)[0].decode('utf-8')
			summary['SERVICES'].append(s)
			output['SERVICE_%s_TAG_%s' % (name, service2env(tagname))] = [value]


def readtags():
	if 'SERVICES' not in summary:
		summary['SERVICES'] = []

	for s in services:
		path = '%s/%s/%s' % (base, s, hostname)
		name = service2env(s)
		if zk.exists(path):
			children = zk.retry(zk.get_children, path)
			for t in children:
				value = zk.retry(zk.get, '%s/%s' % (path, t))[0].decode('utf-8')
				output['SERVICE_%s_TAG_%s' % (name, service2env(t))] = [value]
			if children:
				summary['SERVICES'].append(s)


def untag(tagname):
	if not services:
		return
	if 'MODIFIED' not in summary:
		summary['MODIFIED'] = []

	for s in services:
		path = '%s/%s/%s/%s' % (base, s, hostname, tagname)
		name = service2env(s)
		if zk.exists(path):
			if not dry:
				zk.retry(zk.delete, path)
			summary['MODIFIED'].append(s)
			output['MODIFIED_%s' % name] = [hostname]


def create_file(dest):
	if not os.path.exists(os.path.dirname(dest)):
		os.makedirs(os.path.dirname(dest))
	return open(dest, 'w')


def create_from_stream(stream, dest, mode = 0644):
	with create_file(dest) as f:
		for line in stream.readlines():
			f.write(line)
	os.chmod(dest, mode)


def deploy():
	ok = True
	cron_minutes = random.randrange(0, 60)
	destdir = os.getenv('DESTDIR', '/')
	req = pkg_resources.Requirement.parse('zoosync')

	try:
		has_systemd = subprocess.call(['pkg-config', '--exists', 'systemd'])
	except OSError, e:
		if e.errno == 2:
			print >> sys.stderr, 'pkg-config required'
			return False
		else:
			raise

	if has_systemd == 0:
		# SystemD unit file
		dest = os.path.join(destdir, 'etc/systemd/system', 'zoosync.service')
		fs = pkg_resources.resource_stream(req, "zoosync/scripts/zoosync.service")
		create_from_stream(fs, dest, 0644)
		if not dry:
			if subprocess.call(['systemctl', 'daemon-reload']) != 0:
				print >> sys.stderr, 'systemctl daemon-reload failed'
				ok = False
			if subprocess.call(['systemctl', 'enable', 'zoosync']) != 0:
				print >> sys.stderr, 'Enabling zoosync service failed'
				ok = False
	else:
		# SystemV startup script
		dest = os.path.join(destdir, 'etc/init.d', 'zoosync')
		fs = pkg_resources.resource_stream(req, "zoosync/scripts/zoosync.sh")
		create_from_stream(fs, dest, 0755)
		if not dry:
			if os.path.exists('/etc/redhat-release'):
				if subprocess.call(['chkconfig', 'zoosync', 'on']) != 0:
					print >> sys.stderr, 'Enabling zoosync service failed'
					ok = False
			else:
				if subprocess.call(['update-rc.d', 'zoosync', 'defaults']) != 0:
					print >> sys.stderr, 'Enabling zoosync service failed'
					ok = False

	dest = os.path.join(destdir, 'etc/cron.d', 'zoosync')
	with create_file(dest) as f:
		f.write('%s 0 * * *	service zoosync start >/dev/null 2>/dev/null || :\n' % cron_minutes)

	dest = os.path.join(destdir, 'etc', 'zoosyncrc')
	if not os.path.exists(dest):
		with create_file(dest) as f:
			f.write('zookeeper=%s\nbase=%s\nuser=%s\npassword=%s\nacl=%s\n' % (zookeeper_hosts, base, user, password, admin_acl))
		os.chmod(dest, 0600)

	if services:
		dest = os.path.join(destdir, 'etc', 'default', 'zoosync')
		if not os.path.exists(dest):
			with create_file(dest) as f:
				f.write('SERVICES=%s\n' % ','.join(services))

	return ok


def parse_option(opt = None, arg = None, key = None, value = None):
	global base, admin_acl, dry, hostname, zookeeper_hosts, multi, user, password, services, wait_time

	if opt in ['-h', '--help']:
		usage()
		sys.exit(0)
	elif opt in ['-a', '--acl'] or key in ['acl', 'acl']:
		admin_acl = arg
	elif opt in ['-n', '--dry'] or key in ['dry']:
		dry = True
	elif opt in ['-H', '--hostname'] or key in ['hostname']:
		hostname = arg
	elif opt in ['-b', '--base'] or key in ['base']:
		base = arg
	elif opt in ['-m', '--multi'] or key in ['multi']:
		if arg in ['random', 'round-robin']:
			multi = MULTI_RANDOM
		elif arg in ['all', 'list']:
			multi = MULTI_LIST
		else:
			multi = MULTI_FIRST
	elif opt in ['-u', '--user'] or key in ['user']:
		user = arg
	elif opt in ['-w', '--wait'] or key in ['wait']:
		wait_time = int(arg)
	elif opt in ['-p', '--password'] or key in ['password']:
		password = arg
	elif opt in ['-s', '--services'] or key in ['services']:
		if arg:
			services = re.split(',', arg)
		else:
			services = []
	elif opt in ['-z', '--zookeeper'] or key in ['zookeeper', 'hosts']:
		zookeeper_hosts = arg


def setUp(argv, remaining_args = None):
	global zk, myAcl, adminAcls, hiddenAcls
	f = None

	config_file = os.getenv('ZOOSYNC_CONF', '/etc/zoosyncrc')
	try:
		f = open(config_file, 'r')
	except:
		pass
	if f:
		for line in f:
			line = line.rstrip('\r\n')
			if re.match(r'^\s*#.*', line):
				continue
			keyvalue = re.split(r'\s*=\s*', line, 1)
			key = keyvalue[0]
			if len(keyvalue) > 1:
				value = keyvalue[1]
			else:
				value = None
			parse_option(key = key, arg = value)
		f.close()

	try:
		opts, args = getopt.getopt(argv, 'ha:b:H:m:np:s:u:vw:z:',['help', 'acl=', 'base=', 'hostname=', 'dry', 'multi=', 'user=', 'password=', 'services=', 'version', 'wait=', 'zookeeper='])
	except getopt.GetoptError:
		print 'Error parsing arguments'
		usage()
		sys.exit(2)
	for opt, arg in opts:
		if opt in ['-h', '--help']:
			usage()
			sys.exit(0)
		elif opt in ['-v', '--version']:
			print version.__version__
			sys.exit(0)
		parse_option(opt = opt, arg = arg)

	logging.basicConfig()

	myAcl = make_digest_acl(user, password, all=True)
	if admin_acl:
		admin_acl_list = re.split(',', admin_acl)
		for s in admin_acl_list:
			acl = str2acl(s);
			if acl:
				adminAcls += [acl]
			acl = str2acl(s, hidden = True);
			if acl:
				hiddenAcls += [acl]

	#print '# Admin ACL: %s' % adminAcls
	#print '# Secret ACL: %s' % hiddenAcls

	zk = KazooClient(
		zookeeper_hosts,
		auth_data=[('digest', '%s:%s' % (user, password))]
	)
	
	zk.start()

	if remaining_args != None:
		remaining_args.extend(args)


def tearDown():
		zk.stop()


def main(argv=sys.argv[1:]):
	args = []
	retval = 0

	setUp(argv, args)

	try:
		if not dry:
			zk.retry(zk.ensure_path, base, adminAcls + [myAcl])

		for command in args:
			if command == 'deploy':
				if not deploy():
					retval = 1
			elif command == 'get':
				get(multi)
			elif command == 'remove':
				remove()
			elif command == 'cleanup':
				cleanup()
			elif command == 'create':
				create(strict = True)
			elif command == 'list':
				list()
			elif command == 'purge':
				purge()
			elif command == 'register':
				create(strict = False)
			elif command == 'tag':
				for t in args[1:]:
					tagname, tagvalue = re.split('=', t, 1)
					tag(tagname, tagvalue)
			elif command == 'read-tag':
				for t in args[1:]:
					readtag(t)
			elif command == 'read-tags' or command == 'tags':
				readtags()
			elif command == 'unregister':
				unregister()
			elif command == 'untag':
				for t in args[1:]:
					untag(t)
			elif command == 'wait':
				wait()
	finally:
		tearDown()

	for key in sorted(output.keys()):
		print '%s=%s' % (key, ','.join(output[key]))
	for key in summary.keys():
		if summary[key]:
			print '%s=%s' % (key, ','.join(summary[key]))
		else:
			print '%s=' % key

	return retval


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
