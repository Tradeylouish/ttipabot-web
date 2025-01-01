from flask import render_template, request, jsonify
from app import app
import ttipabot.app as tt

@app.route('/')
def serve_page(): 
    return render_template('page.html', request=request)

@app.route('/data')
def data_api(): 
    tt.scrape_register()
    dates = tt.get_dates(num=2, oldest=False, changesOnly=True)
    names = tt.compare_registrations(dates, raw=True, pat=True, tm=False)
    return jsonify(names)