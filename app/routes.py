from flask import render_template, request, jsonify, Response
from app import app
import ttipabot


def get_filters(args) -> tuple[bool, bool]:
    filters = args.getlist('filter')
    pat = 'pat' in filters
    tm = 'tm' in filters
    return pat, tm

@app.route('/')
def serve_page(): 
    return render_template('page.html', request=request)

@app.route('/api/registrations')
def registrations_api(): 
    pat, tm = get_filters(request.args)
    dates = ttipabot.get_dates(num=2, oldest=False, changesOnly=True)
    attorneys = ttipabot.compare_data(dates, pat=pat, tm=tm, mode='registrations', json=True)
    return Response(attorneys, mimetype='application/json')

@app.route('/api/movements')
def movements_api():
    pat, tm = get_filters(request.args)
    dates = ttipabot.get_dates(num=2, oldest=False, changesOnly=True)
    attorneys = ttipabot.compare_data(dates, pat=pat, tm=tm, mode='movements', json=True)
    return Response(attorneys, mimetype='application/json')

@app.route('/api/lapses')
def lapses_api():
    pat, tm = get_filters(request.args)
    dates = ttipabot.get_dates(num=2, oldest=False, changesOnly=True)
    attorneys = ttipabot.compare_data(dates, pat=pat, tm=tm, mode='lapses', json=True)
    return Response(attorneys, mimetype='application/json')

@app.route('/api/names')
def attorneys_api():
    pat, tm = get_filters(request.args)
    date = request.args.get('date')
    if not date:
        date = ttipabot.get_latest_date()
    attorneys = ttipabot.rank_data(date, num=10, pat=pat, tm=tm, mode='names', json=True)
    return Response(attorneys, mimetype='application/json')

@app.route('/api/firms')
def firms_api():
    pat, tm = get_filters(request.args)
    date = request.args.get('date')
    if not date:
        date = ttipabot.get_latest_date()
    firms = ttipabot.rank_data(date, num=10, pat=pat, tm=tm, mode='firms', json=True)
    return Response(firms, mimetype='application/json')