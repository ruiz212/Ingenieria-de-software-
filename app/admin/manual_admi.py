from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import json
import traceback

from app.admin import admin_bp
from app.db import get_db_connection, execute_sp
from app.auth.decorators import roles_required
from app.extensions import csrf
from datetime import datetime, timedelta


@admin_bp.route('/manual_admin', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def manual_admin():
    roles_db = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            execute_sp(
                cursor,
                'seguridad.sp_ListarRoles',
                (),
                fallback_sql="SELECT ID, Nombre FROM Roles ORDER BY ID",
            )
            roles_db = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
    except Exception:
        roles_db = []

    sorted_roles = sorted(roles_db, key=lambda x: x[1])
    return render_template('manual.html', roles=sorted_roles)
