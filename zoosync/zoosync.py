#! /usr/bin/python

import logging
import getopt
import os
import re
import socket
import sys
import subprocess
import threading
import time
import Queue
from kazoo.client import KazooClient
from kazoo.security import make_digest_acl, make_acl

N_PING_THREADS = 4

hosts = 'localhost:2181'
base = '/indigo-testbed'
dry = False
user = 'indigo-testbed'
password = 'changeit'
services = []

hostname = socket.getfqdn()
poll_interval=10
zk = None
myAcl = None
worldAcl = None

output = {}
summary = {}

q_active = Queue.Queue()
q_inactive = Queue.Queue()


def usage():
	print 'Usage: %s [OPTIONS] commands\n\
OPTIONS:\n\
  -h, --help ......... usage message\n\
  -b, --base ......... base zookeeper directory\n\
  -H, --hosts ........ comma separated list of hosts\n\
  --hostname ......... use specified hostname\n\
  -n, --dry .......... read-only network operations\n\
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


#
# threaded pinger
#
# http://stackoverflow.com/questions/316866/ping-a-site-in-python
def pinger(i, q):
	while True:
		s, ip = q.get()
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
			q_active.put([s, ip])
		else:
			#print '%s dead' % ip
			q_inactive.put([s, ip])
		q.task_done()


def remove(force = False):
	global output, summary, hostname

	if not services:
		return
	if 'REMOVED' not in summary:
		summary['REMOVED'] = []

	for s in services:
		path = '%s/%s' % (base, s)
		if zk.exists(path):
			value = zk.retry(zk.get, path)[0].decode('utf-8')
			if value == hostname or force:
				if not dry:
					zk.retry(zk.delete, path)
				summary['REMOVED'].append(s)
				output['REMOVED_%s' % service2env(s)] = value
			else:
				output['SERVICE_%s' % service2env(s)] = value


def get():
	if not services:
		return
	if 'SERVICES' not in summary:
		summary['SERVICES'] = []
	if 'MISSING' not in summary:
		summary['MISSING'] = []

	for s in services:
		path = '%s/%s' % (base, s)
		name = service2env(s)
		if zk.exists(path):
			value = zk.retry(zk.get, path)[0].decode('utf-8')
			summary['SERVICES'].append(s)
			output['SERVICE_%s' % name] = value
		else:
			summary['MISSING'].append(s)


def cleanup():
	queue = Queue.Queue()

	if 'REMOVED' not in summary:
		summary['REMOVED'] = []
	get()

	for i in range(N_PING_THREADS):
		worker = threading.Thread(target=pinger, args=(i, queue))
		worker.setDaemon(True)
		worker.start()

	for s in summary['SERVICES']:
		name = service2env(s)
		ip = output['SERVICE_%s' % name]
		queue.put([s, ip])
	queue.join()

	# cleanups:
	#   1) remove from zookeeper
	#   2) remove from SERVICES
	#   3) add to REMOVED
	#   4) add to MISSSING (it's removed!)
	while not q_inactive.empty():
		s, ip = q_inactive.get()
		path = '%s/%s' % (base, s)
		name = service2env(s)
		value = output['SERVICE_%s' % name]

		if not dry:
			zk.retry(zk.delete, path)

		del output['SERVICE_%s' % name]
		summary['REMOVED'].append(s)
		output['REMOVED_%s' % name] = value
		summary['MISSING'].append(s)
		output['MISSING_%s' % name] = value

		q_inactive.task_done()

	summary['SERVICES'] = []
	while not q_active.empty():
		s, ip = q_active.get()
		name = service2env(s)
		summary['SERVICES'].append(s)
		q_active.task_done()


def list():
	if 'SERVICES' not in summary:
		summary['SERVICES'] = []

	children = zk.retry(zk.get_children, base)
	for s in sorted(children):
		path = '%s/%s' % (base, s)
		name = service2env(s)
		value = zk.retry(zk.get, path)[0].decode('utf-8')
		summary['SERVICES'].append(s)
		output['SERVICE_%s' % name] = value


def wait():
	if not services:
		return

	ok=False
	while not ok:
		ok=True
		for s in services:
			if not zk.exists('%s/%s' % (base, s)):
				ok=False
				time.sleep(poll_interval)
				break
	get()
	if not summary['MISSING']:
		del summary['MISSING']


def create(strict = True):
	global hostname

	if not services:
		return
	if 'SERVICES' not in summary:
		summary['SERVICES'] = []

	for s in services:
		path = '%s/%s' % (base, s)
		name = service2env(s)
		value = None
		if not strict and zk.exists(path):
			value = zk.retry(zk.get, path)[0].decode('utf-8')
		if not dry and not value:
			zk.retry(zk.create, path, hostname, [myAcl, worldAcl])
			value = hostname
		summary['SERVICES'].append(s)
		output['SERVICE_%s' % name] = value


def parse_option(opt = None, arg = None, key = None, value = None):
	global base, dry, hostname, hosts, user, password, services

	if opt in ['-h', '--help']:
		usage()
		sys.exit(0)
	elif opt in ['-n', '--dry'] or key in ['dry']:
		dry = True
	elif opt in ['--hostname'] or key in ['hostname']:
		hostname = arg
	elif opt in ['-H', '--hosts'] or key in ['hosts']:
		hosts = arg
	elif opt in ['-b', '--base'] or key in ['base']:
		base = arg
	elif opt in ['-u', '--user'] or key in ['user']:
		user = arg
	elif opt in ['-p', '--password'] or key in ['password']:
		password = arg
	elif opt in ['-s', '--services'] or key in ['services']:
		services = re.split(',', arg)


def main(argv=sys.argv[1:]):
	global zk, myAcl, worldAcl
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
		opts, args = getopt.getopt(argv, 'hb:H:nu:p:s:',['help', 'base=', 'hostname=', 'hosts=', 'dry', 'user=', 'password=', 'services='])
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
	worldAcl = make_acl('world', 'anyone', read=True)
	
	zk = KazooClient(
		hosts,
		auth_data=[('digest', '%s:%s' % (user, password))]
	)
	
	zk.start()
	
	try:
		zk.retry(zk.ensure_path, base, [myAcl, worldAcl])

		for command in args:
			if command == 'get':
				get()
			elif command == 'remove':
				remove(force = True)
			elif command == 'cleanup':
				cleanup()
			elif command == 'create':
				create(strict = True)
			elif command == 'list':
				list()
			elif command == 'register':
				create(strict = False)
			elif command == 'unregister':
				remove(force = False)
			elif command == 'wait':
				wait()
	finally:
		zk.stop()

	for key in sorted(output.keys()):
		print '%s=%s' % (key, output[key])
	for key in summary.keys():
		if summary[key]:
			print '%s=%s' % (key, ','.join(summary[key]))
		else:
			print '%s=' % key


if __name__ == "__main__":
   main(sys.argv[1:])
