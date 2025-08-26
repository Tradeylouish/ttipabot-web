from flask import render_template, request

from app.main import bp


@bp.route('/')
def index(): 
    return render_template('page.html', request=request)