from __future__ import unicode_literals

from datetime import datetime
import os
import platform

from fabric.api import env, execute, hosts, settings, task, prefix
from fabric.colors import green, red
from fabric.contrib.project import rsync_project
from fabric.utils import abort, puts

from fabfile import confirm, run_local, require_env, require_services
from fabfile.utils import get_random_string


@task
@hosts('')
@require_services
def setup():
    """Initial setup of the project. Use ``setup_with_production_data`` instead
    if the project is already installed on a server"""
    if os.path.exists('venv'):
        puts(red('It seems that this project is already set up, aborting.'))
        return 1

    execute('local.create_virtualenv')
    execute('local.update_requirement_files')
    execute('local.frontend_tools')
    execute('local.create_dotenv')
    execute('local.create_and_migrate_database')

    puts(green(
        'Initial setup has completed successfully!', bold=True))
    puts(green(
        'Next steps:'))
    puts(green(
        '- Update the README: edit README.rst'))
    puts(green(
        '- Create a superuser: venv/bin/python manage.py createsuperuser'))
    puts(green(
        '- Run the development server: fab dev'))
    puts(green(
        '- Create a Bitbucket repository: fab git.init_bitbucket'))
    puts(green(
        '- Configure a server for this project: fab server.setup'
        % env))


@task
@require_env
@require_services
def setup_with_production_data():
    """Installs all dependencies and pulls the database and mediafiles from
    the server to create an instant replica of the production environment"""
    if os.path.exists('venv'):
        puts(red('It seems that this project is already set up, aborting.'))
        return 1

    execute('local.create_virtualenv')
    execute('local.frontend_tools')
    execute('local.create_dotenv')
    execute('local.pull_database')
    execute('local.empty_to_password')
    execute('local.pull_mediafiles')

    puts(green(
        'Setup with production data has completed successfully!', bold=True))
    puts(green(
        'Next steps:'))
    puts(green(
        '- Create a superuser: venv/bin/python manage.py createsuperuser'))
    puts(green(
        '- Run the development server: fab dev'))


@task
@hosts('')
@require_services
def update():
    run_local('venv/bin/pip install -r requirements/dev.txt')
    execute('local.frontend_tools')
    run_local('venv/bin/python manage.py migrate')


@task
@hosts('')
def create_virtualenv():
    """Creates the virtualenv and installs all Python requirements"""
    run_local(
        'virtualenv --python %(box_python)s'
        ' --prompt "(venv:%(box_domain)s)" venv')
    run_local('venv/bin/pip install -U wheel setuptools pip')
    if platform.system() == 'Darwin' and platform.mac_ver()[0] >= '10.9':
        run_local(
            'export CFLAGS=-Qunused-arguments'
            ' && export CPPFLAGS=-Qunused-arguments'
            ' && venv/bin/pip install -r requirements/dev.txt')
    else:
        run_local('venv/bin/pip install -r requirements/dev.txt')


@task
@hosts('')
def update_requirement_files():
    """ Updates requirement files with specific version numbers """
    with prefix('. venv/bin/activate'):
        # We need to pass the files manually to ensure common.txt comes
        # first (It's extended with  all packages not defined in any other
        # requirement file). We also have to exclude production.txt
        # because every package not installed will get lost (and the
        # production packages are of course not installed).
        run_local(
            'venv/bin/pip-dump requirements/common.txt requirements/dev.txt')


@task
@hosts('')
def frontend_tools():
    """Installs frontend tools. Knows how to handle npm/bower and bundler"""
    if os.path.exists('package.json'):
        run_local('npm install')
    if os.path.exists('bower.json'):
        run_local('bower install')
    if os.path.exists('%(box_staticfiles)s/bower.json' % env):
        run_local('cd %(box_staticfiles)s && npm install')
        run_local('cd %(box_staticfiles)s && bower install')
    if os.path.exists('Gemfile'):
        run_local('bundle install --path=.bundle/gems')

    if not os.path.exists('%(box_staticfiles)s/bower_components' % env):
        return

    if not os.path.exists('%(box_staticfiles)s/scss/_settings.scss' % env):
        run_local(
            'cp %(box_staticfiles)s/bower_components/foundation/scss/'
            'foundation/_settings.scss %(box_staticfiles)s/scss/')
        puts(red(
            'Please commit %(box_staticfiles)s/scss/_settings.scss if you'
            ' intend to modify this file!' % env))
    else:
        puts(red(
            'Not replacing %(box_staticfiles)s/scss/_settings.scss with'
            ' Foundation\'s version, file exists already.' % env))


@task
@hosts('')
def create_dotenv():
    """Creates a .env file containing basic configuration for
    local development"""
    with open('.env', 'w') as f:
        env.box_secret_key = get_random_string(50)
        f.write('''\
DJANGO_SETTINGS_MODULE=%(box_project_name)s.settings.local
DATABASE_URL=postgres://localhost:5432/%(box_database_local)s
CACHE_URL=hiredis://localhost:6379/1/?key_prefix=%(box_database_local)s
SECRET_KEY=%(box_secret_key)s
SENTRY_DSN=
ALLOWED_HOSTS=['*']
''' % env)


@task
@hosts('')
@require_services
def create_and_migrate_database():
    """Creates and migrates a Postgres database"""

    if not confirm(
            'Completely replace the local database'
            ' "%(box_database_local)s" (if it exists)?'):
        return

    run_local(
        'dropdb --if-exists %(box_database_local)s')
    run_local(
        'createdb %(box_database_local)s'
        ' --encoding=UTF8 --template=template0')
    with settings(warn_only=True):
        run_local('venv/bin/python manage.py makemigrations elephantblog')
        run_local('venv/bin/python manage.py makemigrations page')
    run_local('venv/bin/python manage.py migrate')


@task
@require_env
@require_services
def pull_database():
    """Pulls the database contents from the server, dropping the local
    database first (if it exists)"""

    if not confirm(
            'Completely replace the local database'
            ' "%(box_database_local)s" (if it exists)?'):
        return

    run_local(
        'dropdb --if-exists %(box_database_local)s')
    run_local(
        'createdb %(box_database_local)s'
        ' --encoding=UTF8 --template=template0')
    run_local(
        'ssh %(host_string)s "source .profile &&'
        ' pg_dump %(box_database)s'
        ' --no-privileges --no-owner --no-reconnect"'
        ' | psql %(box_database_local)s')


@task
@require_env
@require_services
def empty_to_password():
    run_local(
        'venv/bin/python manage.py update_empty_passwords password')
    puts(green(
        'Users with empty passwords (for example SSO users) now have a'
        ' password of "password" (without quotes).'))


@task
@require_env
def pull_mediafiles():
    """Pulls all mediafiles from the server. Beware, it is possible that this
    command pulls down several GBs!"""
    if not confirm('Completely replace local mediafiles?'):
        return
    rsync_project(
        local_dir='media/',
        remote_dir='%(box_domain)s/media/' % env,
        delete=False,  # Devs can take care of their media folders.
        upload=False,
    )


@task
@require_env
@require_services
def pull():
    execute('local.pull_database')
    execute('local.pull_mediafiles')
    execute('local.empty_to_password')
    execute('local.update')


@task
@require_env
@require_services
def dump_db():
    """Dumps the database into the tmp/ folder"""
    env.box_datetime = datetime.now().strftime('%Y-%m-%d-%s')
    env.box_dump_filename = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'tmp',
        '%(box_database)s-local-%(box_datetime)s.sql' % env,
    )

    run_local(
        'pg_dump %(box_database_local)s --no-privileges --no-owner'
        ' --no-reconnect > %(box_dump_filename)s')
    puts(green('\nWrote a dump to %(box_dump_filename)s' % env))


@task
@require_env
@require_services
def load_db(filename=None):
    """Loads a dump into the database"""
    env.box_dump_filename = filename

    if not filename:
        abort(red('Dump missing. "fab local.load_db:filename"', bold=True))

    if not os.path.exists(filename):
        abort(red('"%(box_dump_filename)s" does not exist.' % env, bold=True))

    run_local('dropdb --if-exists %(box_database_local)s')
    run_local(
        'createdb %(box_database_local)s'
        ' --encoding=UTF8 --template=template0')
    run_local('psql %(box_database_local)s < %(box_dump_filename)s')
