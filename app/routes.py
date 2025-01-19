from flask import render_template, request, jsonify, Response
from app import app
import ttipabot

@app.route('/')
def serve_page(): 
    return render_template('page.html', request=request)

@app.route('/api/registrations')
def registrations_api(): 
    dates = ttipabot.get_dates(num=2, oldest=False, changesOnly=True)
    attorneys = ttipabot.compare_data(dates, pat=True, tm=False, mode='registrations', json=True)
    return Response(attorneys, mimetype='application/json')

@app.route('/api/movements')
def movements_api(): 
    dates = ttipabot.get_dates(num=2, oldest=False, changesOnly=True)
    attorneys = ttipabot.compare_data(dates, pat=False, tm=False, mode='movements', json=True)
    return Response(attorneys, mimetype='application/json')

@app.route('/api/lapses')
def lapses_api(): 
    dates = ttipabot.get_dates(num=2, oldest=False, changesOnly=True)
    attorneys = ttipabot.compare_data(dates, pat=False, tm=False, mode='lapses', json=True)
    return Response(attorneys, mimetype='application/json')

@app.route('/api/names')
def attorneys_api(): 
    date = ttipabot.get_latest_date()
    attorneys = ttipabot.rank_data(date, num=10, pat=False, tm=False, mode='names', json=True)
    return Response(attorneys, mimetype='application/json')

@app.route('/api/firms')
def firms(): 
    date = ttipabot.get_latest_date()
    firms = ttipabot.rank_data(date, num=10, pat=False, tm=False, mode='firms', json=True)
    return Response(firms, mimetype='application/json')