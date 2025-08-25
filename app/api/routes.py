import datetime

import sqlalchemy as sa
from flask import request, url_for

from app import db, queries
from app.api import bp
from app.models import Attorney, Firm


def get_filters(args) -> tuple[bool, bool]:
    filters = args.getlist('filter')
    pat = 'pat' in filters
    tm = 'tm' in filters
    return pat, tm

def to_date(date_str: str) -> str:
    return datetime.date.fromisoformat(date_str)

@bp.route('/registrations')
def registrations():
    pat, tm = get_filters(request.args)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    first_date = request.args.get('first_date', datetime.date.today() - datetime.timedelta(days=7), type=toDate)
    last_date = request.args.get('last_date', datetime.date.today(), type=toDate)

    query = queries.get_registrations_query(first_date, last_date, pat, tm)
    
    endpoint_kwargs = {
        'first_date': first_date.isoformat(),
        'last_date': last_date.isoformat(),
        'filter': request.args.getlist('filter')
    }
    return Attorney.to_collection_dict(query, page, per_page, 'api.registrations', **endpoint_kwargs)


@bp.route('/movements')
def movements():
    pat, tm = get_filters(request.args)
    first_date = request.args.get('first_date', datetime.date.today() - datetime.timedelta(days=7), type=toDate)
    last_date = request.args.get('last_date', datetime.date.today(), type=toDate)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    query = queries.get_movements_query(first_date, last_date, pat, tm)
    
    resources = db.paginate(query, page=page, per_page=per_page, error_out=False)

    items = []
    for old_rec, new_rec in resources.items:
        items.append({
            'attorney_name': new_rec.name,
            'external_id': new_rec.external_id,
            'movement_date': new_rec.valid_from.isoformat(),
            'from_firm': {
                'name': old_rec.firm,
                'address': old_rec.address
            },
            'to_firm': {
                'name': new_rec.firm,
                'address': new_rec.address
            }
        })

    endpoint_kwargs = {
        'filter': request.args.getlist('filter')
    }
    if first_date:
        endpoint_kwargs['first_date'] = first_date.isoformat()
    if last_date:
        endpoint_kwargs['last_date'] = last_date.isoformat()

    response = {
        'items': items,
        '_meta': {
            'page': page,
            'per_page': per_page,
            'total_pages': resources.pages,
            'total_items': resources.total
        },
        '_links': {
            'self': url_for('api.movements', page=page, per_page=per_page, **endpoint_kwargs),
            'next': url_for('api.movements', page=page + 1, per_page=per_page, **endpoint_kwargs) if resources.has_next else None,
            'prev': url_for('api.movements', page=page - 1, per_page=per_page, **endpoint_kwargs) if resources.has_prev else None
        }
    }
    return response

@bp.route('/lapses')
def lapses():
    pat, tm = get_filters(request.args)
    first_date_str = request.args.get('first_date')
    last_date_str = request.args.get('last_date')
    first_date = datetime.date.today() - datetime.timedelta(days=7) if not first_date_str else datetime.date.fromisoformat(first_date_str)
    last_date = datetime.date.today() if not last_date_str else datetime.date.fromisoformat(last_date_str)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    query = queries.get_lapses_query(first_date, last_date, pat, tm)
    
    endpoint_kwargs = {
        'first_date': first_date.isoformat(),
        'last_date': last_date.isoformat(),
        'filter': request.args.getlist('filter')
    }
    return Attorney.to_collection_dict(query, page, per_page, 'api.lapses', **endpoint_kwargs)

@bp.route('/attorneys')
def attorneys():
    pat, tm = get_filters(request.args)
    date = request.args.get('date', default=datetime.date.today(), type=to_date)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    order_by_param = request.args.get('orderBy', default='-name_length', type=str) 

    query = queries.get_attorneys_query(date, order_by_param, pat, tm)

    endpoint_kwargs = {
        'date': date.isoformat(),
        'filter': request.args.getlist('filter'),
        'orderBy': order_by_param
    }
    return Attorney.to_collection_dict(query, page, per_page, 'api.attorneys', **endpoint_kwargs)

@bp.route('/firms')
def firms():
    pat, tm = get_filters(request.args)
    date = request.args.get('date', default=datetime.date.today(), type=to_date)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 1, type=int)
    order_by_param = request.args.get('orderBy', default='+name', type=str) 

    query = queries.get_firms_query(date, order_by_param, pat, tm)
    
    endpoint_kwargs = {
        'date': date.isoformat(),
        'filter': request.args.getlist('filter'),
        'orderBy': order_by_param
    }

    return Firm.to_collection_dict(query, page, per_page, 'api.firms', **endpoint_kwargs)