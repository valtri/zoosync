#!/bin/sh
### BEGIN INIT INFO
# Provides:          zoosync
# Required-Start:    $local_fs $network $named
# Required-Stop:     $local_fs $network $named
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# X-Interactive:     true
# Short-Description: Register/unregister services in Zookeeper
### END INIT INFO

PATH=/usr/bin:/usr/sbin:/bin:/sbin:/usr/local/bin:/usr/local/sbin
. /lib/lsb/init-functions

if [ -f /etc/default/zoosync ] ; then
	. /etc/default/zoosync
fi

case $1 in
	start)
		log_daemon_msg "Registering" "zoosync"
		out="`zoosync -s ${SERVICES} create`"
                log_end_msg $?
		;;
	stop)
		log_daemon_msg "Unregistering" "zoosync"
		out="`zoosync -s ${SERVICES} remove`"
                log_end_msg $?
		;;
	reload|restart|force-reload)
		zoosync -s ${SERVICES} remove >/dev/null
		out="`zoosync -s ${SERVICES} create`"
                log_end_msg $?
		;;
	status)
		zoosync -s ${SERVICES} get
		;;
	*)
		log_success_msg "Usage: /etc/init.d/zoosync {start|stop|restart|reload|force-reload|status}"
		exit 1
		;;
esac

echo -n "$out"
