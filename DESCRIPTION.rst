Zoosync
=======

Zoosync is a simple service discovery tool using Zookeeper as database backend.

Usage
=====

See `zoosync --help` for brief usage or manual page for more detailed usage.

The output is in the form of shell variable assignement, so tool could be used this way::

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

  # configure

  cat > /etc/zoosyncrc <<EOF
  zookeeper=zoo1,zoo2,zoo3
  user=user
  password=changeit
  services=service1,service2
  EOF

  # automatic startup

  # 1) SystemV

  cp scripts/zoosync.sh /etc/init.d/
  #debian: update-rc.d zoosync defaults
  #redhat: chkconfig zoosync on

  # 2) SystemD

  cp scripts/zoosync.service /etc/systemd/system/
  systemctl enable zoosync
