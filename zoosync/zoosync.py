#! /usr/bin/python

import logging
import getopt
import os
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

N_PING_THREADS = 4

MULTI_FIRST = 1
MULTI_RANDOM = 2
MULTI_LIST = 3

hosts = 'localhost:2181'
base = '/indigo-testbed'
dry = False
multi = MULTI_FIRST
user = 'indigo-testbed'
password = 'changeit'
services = []
admin_acl = 'world:anyone:r'

hostname = socket.getfqdn()
poll_interval=10
zk = None
adminAcls = []
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
  -H, --hosts ........ comma separated list of hosts\n\
  --hostname ......... use specified hostname\n\
  -m, --multi .......  selection from multiple endpoints\n\
  -u, --user ......... user\n\
  -p, --password ..... password\n\
  -s, --services ..... comma separated list of services\n\
COMMANDS:\n\
  list ....... get all services\n\
  get   ...... get given services\n\
  cleanup .... get given services (only active), remove inactive\n\
  create ..... create a service\n\
  register ... register a service\n\
  remove ..... remove given services\n\
  unregister . unregister services\n\
  wait ......  wait for given services\n\
' % sys.argv[0]


def service2env(s):
	return re.sub(r'[\.-]', r'_', s.upper())


def str2acl(s):
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
		if re.search('r', permissions):
			read = True
		if re.search('w', permissions):
			write = True
		if re.search('a', permissions):
			admin = True
		return make_acl(scheme, credential, create = create, delete = delete, read = read, write = write, admin = admin)
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


def zoo_skeleton(path):
	if not dry:
		zk.retry(zk.ensure_path, path, adminAcls + [myAcl])


def zoo_hostnames(path, multi):
	children = sorted(zk.retry(zk.get_children, path))
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

	for ip in service_hostnames.keys():
		queue.put([ip, service_hostnames[ip]])
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
	for s in sorted(removed_services.keys()):
		output['REMOVED_%s' % s] = sorted(removed_services[s])
	summary['MISSING'] = sorted(missing_services.keys())
	summary['SERVICES'] = sorted(summary_services.keys())
	for s in sorted(summary_services.keys()):
		output['SERVICE_%s' % s] = sorted(summary_services[s])


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
		if strict:
			zoo_skeleton(parent_path)
			if not dry:
				zk.retry(zk.create, path, value = '', acl = adminAcls + [myAcl])
		else:
			zoo_skeleton(path)
		summary['SERVICES'].append(s)
		output['SERVICE_%s' % name] = values


def remove(strict = True):
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
			if strict:
				raise ValueError('service endpoint %s/%s doesn\'t exist' % (s, hostname))


def wait():
	if not services:
		return

	ok=False
	while not ok:
		ok=True
		for s in services:
			path = '%s/%s' % (base, s)
			value = None
			if zk.exists(path):
				values = zoo_hostnames(path, multi)
			if not values:
				ok=False
				time.sleep(poll_interval)
				break
	get(multi)
	if not summary['MISSING']:
		del summary['MISSING']


def parse_option(opt = None, arg = None, key = None, value = None):
	global base, admin_acl, dry, hostname, hosts, multi, user, password, services

	if opt in ['-h', '--help']:
		usage()
		sys.exit(0)
	elif opt in ['-a', '--acl'] or key in ['acl', 'acl']:
		admin_acl = arg
	elif opt in ['-n', '--dry'] or key in ['dry']:
		dry = True
	elif opt in ['--hostname'] or key in ['hostname']:
		hostname = arg
	elif opt in ['-H', '--hosts'] or key in ['hosts']:
		hosts = arg
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
	elif opt in ['-p', '--password'] or key in ['password']:
		password = arg
	elif opt in ['-s', '--services'] or key in ['services']:
		services = re.split(',', arg)


def main(argv=sys.argv[1:]):
	global zk, myAcl, adminAcls
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
		opts, args = getopt.getopt(argv, 'ha:b:H:m:nu:p:s:',['help', 'acl=', 'base=', 'hostname=', 'hosts=', 'dry', 'multi=', 'user=', 'password=', 'services='])
	except getopt.GetoptError:
		print 'Error parsing arguments'
		usage()
		sys.exit(2)
	for opt, arg in opts:
		if opt in ['-h', '--help']:
			usage()
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
	#print '# Admin ACL: %s' % adminAcls

	zk = KazooClient(
		hosts,
		auth_data=[('digest', '%s:%s' % (user, password))]
	)
	
	zk.start()
	
	try:
		if not dry:
			zk.retry(zk.ensure_path, base, adminAcls + [myAcl])

		for command in args:
			if command == 'get':
				get(multi)
			elif command == 'remove':
				remove(strict = True)
			elif command == 'cleanup':
				cleanup()
			elif command == 'create':
				create(strict = True)
			elif command == 'list':
				list()
			elif command == 'register':
				create(strict = False)
			elif command == 'unregister':
				remove(strict = False)
			elif command == 'wait':
				wait()
	finally:
		zk.stop()

	for key in sorted(output.keys()):
		print '%s=%s' % (key, ','.join(output[key]))
	for key in summary.keys():
		if summary[key]:
			print '%s=%s' % (key, ','.join(summary[key]))
		else:
			print '%s=' % key


if __name__ == "__main__":
   main(sys.argv[1:])
