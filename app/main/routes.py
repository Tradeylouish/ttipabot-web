from flask import render_template, request

from app.main import bp


@bp.route('/')
def index(): 
    return render_template('ritual.html', request=request)

@bp.route('/names')
def names():
    return render_template('names.html', request=request)

@bp.route('/movements')
def movements():
    return render_template('movements.html', request=request)

@bp.route('/lapses')
def lapses():
    return render_template('lapses.html', request=request)

@bp.route('/firms')
def firms():
    return render_template('firms.html', request=request)