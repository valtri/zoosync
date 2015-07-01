Zoosync
=======

Zoosync is a simple service discovery tool using Zookeeper as database backend.

Usage
=====

See `zoosync --help` for options.

The output is in the form of shell variable assignement, so tool could be used this way::

 ZOO='zoo1.example.com,zoo2.example.com,zoo3.example.com'
 REQ_SERVICES='impala,hadoop-hdfs,test,test2,test3'

 eval `./zoosync.py --hosts ${ZOO} --services ${REQ_SERVICES} --dry cleanup`

 echo "active: ${SERVICES}"
 echo "missing: ${MISSING}"
