from __future__ import print_function, unicode_literals

from fabric.api import env, execute, lcd, task

from fabfile.config import local


def _coding_style_check(base, project_name):
    """Checks whether there are disallowed debugging statements, and whether
    static checking tools (currently only flake8) report any problems with
    a given project."""
    with lcd(base):
        local("! git grep -n -C3 -E 'import i?pdb' -- '*.py'")
        local("! git grep -n -C3 -E 'console\.log' -- '*.html' '*.js'")
        local(
            "! git grep -n -C3 -E '(^| )print( |\(|$)'"
            " -- '%s/*py'" % project_name)
        local('flake8 .')
        local(
            "jshint $(git ls-files '*.js' | grep -vE '("
            "ckeditor/|lightbox"  # Exclude libraries from JSHint checking.
            ")')")

        with settings(warn_only=True):
            # Remind the user about uglyness, but do not fail (there are good
            # reasons to use the patterns warned about here).
            local("! git grep -n -E '#.*noqa' -- '%s/*.py'" % project_name)


@task(default=True)
def check():
    """Runs coding style checks, and Django's checking framework"""
    _coding_style_check('.', env.box_project_name)
    # _coding_style_check('venv/src/???', '???')
    local('venv/bin/python manage.py check')


@task
def ready():
    """Check whether this project is ready for production"""
    execute('check.check')

    local("! git grep -n -C3 -E '^Disallow: /$' -- 'robots.txt'")
    with lcd(env.box_project_name):
        local("! git grep -n -C3 -E 'meta.*robots.*noindex'")
        local("! git grep -n -C3 -E '(XXX|FIXME|TODO)'")