#!/bin/bash
set -e

POD_NAME=compliance-prototype-test
PG_CONTAINER=${POD_NAME}-postgres
REDIS_CONTAINER=${POD_NAME}-redis
RUNNER_IMAGE=localhost/compliance-prototype-test-runner
PG_PORT=5433
REDIS_PORT=6381
PG_USER=test
PG_PASSWORD=testpass
PG_DB=compliance_test

cmd=${1:-test}

validate() {
  echo "Validating seed data (dry run)"
  python3 scripts/validate_seed_data.py
}

start() {
  echo Creating pod $POD_NAME with ports $PG_PORT and $REDIS_PORT
  podman pod rm -f $POD_NAME 2>/dev/null || true
  podman pod create --name $POD_NAME -p $PG_PORT:5432 -p $REDIS_PORT:6379

  echo Starting postgres
  podman run -d --pod $POD_NAME --name $PG_CONTAINER --replace \
    -e POSTGRES_USER=$PG_USER \
    -e POSTGRES_PASSWORD=$PG_PASSWORD \
    -e POSTGRES_DB=$PG_DB \
    docker.io/library/postgres:15

  echo Starting redis
  podman run -d --pod $POD_NAME --name $REDIS_CONTAINER --replace \
    docker.io/library/redis:7

  echo Building test runner image
  podman build -f podman/Containerfile.test -t $RUNNER_IMAGE .

  echo Waiting for postgres
  until podman exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -c 'SELECT 1' > /dev/null 2>&1; do
    sleep 1
  done
}

seed() {
  echo Loading schema
  podman cp prototype/schema.sql $PG_CONTAINER:/tmp/schema.sql
  podman exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -f /tmp/schema.sql

  echo Loading seed data
  podman run --rm --pod $POD_NAME -v $PWD:/repo:Z \
    -e PGHOST=localhost \
    -e PGPORT=5432 \
    -e PGDATABASE=$PG_DB \
    -e PGUSER=$PG_USER \
    -e PGPASSWORD=$PG_PASSWORD \
    $RUNNER_IMAGE /repo/podman/seed_test_db.py
}

test() {
  validate
  start
  seed
  echo Running assertions
  podman exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -c 'SELECT count(*) AS tenants FROM tenant;' > /dev/null
  podman exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -c 'SELECT count(*) AS common_controls FROM common_control;' > /dev/null
  podman exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -c 'SELECT count(*) AS frameworks FROM framework;' > /dev/null
  podman exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -c 'SELECT count(*) AS resources FROM resource;' > /dev/null
  echo All tests passed
}

stop() {
  echo Stopping test containers
  podman stop -t 2 $PG_CONTAINER $REDIS_CONTAINER 2>/dev/null || true
  podman rm -f $PG_CONTAINER $REDIS_CONTAINER 2>/dev/null || true
  podman pod rm -f $POD_NAME 2>/dev/null || true
}

case $cmd in
  validate) validate ;;
  start) start ;;
  seed) seed ;;
  test) test ;;
  stop) stop ;;
  restart) stop; test ;;
  *) echo Usage: $0 {validate|start|seed|test|stop|restart}; exit 1 ;;
esac
