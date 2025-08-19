import sqlalchemy as sa
from flask import Response, jsonify, render_template, request

from app.main import bp
from app.models import Attorney, Firm


def get_filters(args) -> tuple[bool, bool]:
    filters = args.getlist('filter')
    pat = 'pat' in filters
    tm = 'tm' in filters
    return pat, tm

@bp.route('/')
def serve_page(): 
    return render_template('base.html', request=request)

@bp.route('/api/registrations')
def registrations_api(): 
    pat, tm = get_filters(request.args)
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 100)
    return Attorney.to_collection_dict(sa.select(Attorney), page, per_page, 'registrations_api')


@bp.route('/api/movements')
def movements_api():
    pat, tm = get_filters(request.args)
    first_date = request.args.get('first_date')
    last_date = request.args.get('last_date')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    return Attorney.to_collection_dict(sa.select(Attorney), page, per_page, 'movements_api')

@bp.route('/api/lapses')
def lapses_api():
    pat, tm = get_filters(request.args)
    first_date = request.args.get('first_date')
    last_date = request.args.get('last_date')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    return Attorney.to_collection_dict(sa.select(Attorney), page, per_page, 'lapses_api')

@bp.route('/api/names')
def attorneys_api():
    pat, tm = get_filters(request.args)
    date = request.args.get('date')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page, 10, type=int')
    return Attorney.to_collection_dict(sa.select(Attorney), page, per_page, 'names_api')

@bp.route('/api/firms')
def firms_api():
    pat, tm = get_filters(request.args)
    date = request.args.get('date')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    return Firm.to_collection_dict(sa.select(Firm), page, per_page, 'firms_api')