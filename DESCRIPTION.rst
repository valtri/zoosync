Zoosync
=======

Zoosync is a simple service discovery tool using Zookeeper as database backend.

Usage
=====

See `zoosync --help` for brief usage or manual page for more detailed usage.

The output is in the form of shell variable assignement. Tool could be used this way::

 ZOO='zoo1.example.com,zoo2.example.com,zoo3.example.com'
 REQ_SERVICES='impala,hadoop-hdfs,test,test2,test3'

 zoosync --zookeeper ${ZOO} --services ${REQ_SERVICES} cleanup
 eval `zoosync --zookeeper ${ZOO} --services ${REQ_SERVICES} --wait 1800 wait`

 echo "active: ${SERVICES}"
 echo "missing: ${MISSING}"

Deployment
==========

::

  # install
  pip install zoosync

  # configure (/etc/zoosynrc and startup scripts)
  zoosync -z zoo1,zoo2,zoo3 -s service1,service2 -u user -p password deploy

Tests
=====

Tests require running zookeeper and proper configuration of zoosync (see Usage).

Launch::

   python setup.py test
