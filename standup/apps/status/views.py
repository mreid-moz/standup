from flask import (Blueprint, redirect, render_template, request, session,
                   url_for)
from jinja2.filters import urlize
from markdown import markdown
from urlparse import urljoin
from werkzeug.contrib.atom import AtomFeed

from standup.apps.status.helpers import enddate, paginate, startdate
from standup.apps.status.models import Project, Status
from standup.apps.users.models import Team, User
from standup.errors import forbidden, page_not_found
from standup.filters import format_update
from standup.main import db


blueprint = Blueprint('status', __name__)


def absolute_url(url):
    """Return a non-relative URL; used in XML feeds."""
    return urljoin(request.url_root, url)


def format_status(status):
    """Format a status update inside an Atom feed with HTML filters."""
    return markdown(urlize(format_update(status.content_html, status.project)))


def render_feed(title, statuses):
    """Create an Atom feed from a title and list of statuses."""
    feed = AtomFeed(title, feed_url=request.url, url=request.url_root)

    for status in statuses:
        title = 'From %s at %s' % (status.user.username,
                                   status.created.strftime('%I:%M%p %Z'))
        content = unicode(format_status(status))

        if status.project:
            content = '<h3>%s</h3>%s' % (status.project.name, content)

        feed.add(title, content, content_type='html', author=status.user.name,
                 url=absolute_url(url_for('status.status', id=status.id)),
                 updated=status.created, published=status.created)
    return feed.get_response()


@blueprint.route('/')
def index():
    """The home page."""
    return render_template(
        'index.html',
        statuses=paginate(
            Status.query.filter(Status.reply_to == None).order_by(
                db.desc(Status.created)),
            request.args.get('page', 1),
            startdate(request),
            enddate(request)),)


@blueprint.route('/statuses.xml')
def index_feed():
    """Output every status in an Atom feed."""
    statuses = (Status.query.filter(Status.reply_to == None)
                            .order_by(db.desc(Status.created)))

    return render_feed('All status updates', statuses)


@blueprint.route('/user/<slug>', methods=['GET'])
def user(slug):
    """The user page. Shows a user's statuses."""
    user = User.query.filter_by(slug=slug).first()
    if not user:
        return page_not_found('User not found.')
    return render_template(
        'user.html',
        user=user,
        statuses=user.recent_statuses(
            request.args.get('page', 1),
            startdate(request),
            enddate(request)))


@blueprint.route('/user/<slug>.xml', methods=['GET'])
def user_feed(slug):
    """A user's Atom feed. Output every status from this user."""
    user = User.query.filter_by(slug=slug).first()
    if not user:
        return page_not_found('User not found.')

    statuses = (user.statuses.filter(Status.reply_to == None)
                             .order_by(db.desc(Status.created)))

    return render_feed('Updates by %s' % user.username, statuses)


@blueprint.route('/project/<slug>', methods=['GET'])
def project(slug):
    """The project page. Shows a project's statuses."""
    project = Project.query.filter_by(slug=slug).first()
    if not project:
        return page_not_found('Project not found.')

    return render_template(
        'project.html',
        project=project,
        projects=Project.query.order_by(Project.name).filter(
            Project.statuses.any()),
        statuses=project.recent_statuses(
            request.args.get('page', 1),
            startdate(request),
            enddate(request)))


@blueprint.route('/project/<slug>.xml', methods=['GET'])
def project_feed(slug):
    """Project Atom feed. Shows all statuses for a project."""
    project = Project.query.filter_by(slug=slug).first()
    if not project:
        return page_not_found('Project not found.')

    statuses = (project.statuses.filter(Status.reply_to == None)
                                .order_by(db.desc(Status.created)))

    return render_feed('Updates for %s' % project.name, statuses)


@blueprint.route('/team/<slug>', methods=['GET'])
def team(slug):
    """The team page. Shows statuses for all users in the team."""
    team = Team.query.filter_by(slug=slug).first()
    if not team:
        return page_not_found('Team not found.')

    return render_template(
        'team.html',
        team=team,
        users=team.users,
        teams=Team.query.order_by(Team.name).all(),
        statuses=team.recent_statuses(
            request.args.get('page', 1),
            startdate(request),
            enddate(request)))


@blueprint.route('/team/<slug>.xml', methods=['GET'])
def team_feed(slug):
    """The team status feed. Shows all updates from a team in Atom format."""
    team = Team.query.filter_by(slug=slug).first()
    if not team:
        return page_not_found('Team not found.')

    statuses = (team.statuses().filter(Status.reply_to == None)
                               .order_by(db.desc(Status.created)))

    return render_feed('Updates from %s' % team.name, statuses)


@blueprint.route('/status/<id>', methods=['GET'])
def status(id):
    """The status page. Shows a single status."""
    statuses = Status.query.filter_by(id=id)

    if not statuses.count():
        return page_not_found('Status not found.')

    status = statuses[0]

    return render_template(
        'status.html',
        user=status.user,
        statuses=paginate(statuses),
        replies=status.replies(request.args.get('page', 1))
    )


@blueprint.route('/statusize/', methods=['POST'])
def statusize():
    """Posts a status from the web."""
    email = session.get('email')
    if not email:
        return forbidden('You must be logged in to statusize!')

    user = User.query.filter(User.email == email).first()

    if not user:
        return forbidden('You must have a user account to statusize!')

    message = request.form.get('message', '')

    if not message:
        return page_not_found('You cannot statusize nothing!')

    status = Status(user_id=user.id, content=message, content_html=message)

    project = request.form.get('project', '')
    if project:
        project = Project.query.filter_by(id=project).first()
        if project:
            status.project_id = project.id

    # TODO: reply handling

    db.session.add(status)
    db.session.commit()

    # Try to go back from where we came.
    redirect_url = request.form.get('redirect_to',
        request.headers.get('referer',
            url_for('status.index')))
    return redirect(redirect_url)


@blueprint.route('/profile/', methods=['GET'])
def profile():
    """Shows the user's profile page."""
    email = session.get('email')
    if not email:
        return forbidden('You must be logged in to see a profile!')

    user = User.query.filter(User.email == email).first()

    if not user:
        return forbidden('You must have a user account to see your profile!')

    return render_template(
        'profile.html',
        user=user,
        statuses=user.recent_statuses())