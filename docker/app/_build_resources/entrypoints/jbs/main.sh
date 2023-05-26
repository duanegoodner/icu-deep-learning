#!/bin/bash


source "$(dirname "$0")/startup.sh"
source "$(dirname "$0")/cleanup.sh"


startup() {
  trap 'true' SIGTERM
  trap 'true' SIGINT
  start_rsyslogd
  set_initial_permissions
  sudo service ssh start

}

keep_container_alive() {
  tail -f /dev/null &
  wait $!
}

cleanup() {
  sudo service ssh stop
  reset_permissions
}


main() {
  startup
  keep_container_alive
  cleanup
}

main