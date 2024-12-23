from flask import render_template, flash, redirect, url_for, request
from app import app

@app.route('/')
def serve_page(): 
    return render_template('page.html')