other_commands() {
	docker-compose down
  	exit 0
}


trap 'other_commands' SIGINT
. broker_authentication.sh
docker-compose up
