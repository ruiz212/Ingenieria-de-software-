from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime, timedelta

@admin_bp.route('/manual_admin', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def manual_admin():
   
    return render_template('manual.html')
