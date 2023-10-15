import ast
from enum import Enum
from io import BytesIO
from datetime import datetime

from flask import Flask, request, redirect, url_for, send_file
from flask import render_template
from flask import g

import sqlite3
import qrcode

app = Flask(__name__)

COOKIE = "ert-sm"
DATABASE = "ert-sm"


STATUS_AWAY = "away"


@app.route('/')
def index():  # put application's code here
    if not is_logged_in():
        return render_template('home.html', logged_in=False)

    cookie = ast.literal_eval(request.cookies.get(COOKIE))

    return render_template('home.html', logged_in=True, first_name=cookie.get("first_name"), last_name=cookie.get("last_name"))


@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method != 'POST':
        return render_template('login.html')

    if not is_user(request.form["first_name"], request.form["last_name"]):
        return render_template('login.html')

    # TODO when logging in from QR code: redirect to qr code scan url
    res = redirect('/')
    res.set_cookie(COOKIE, generate_cookie(request.form["first_name"], request.form["last_name"]))
    return res


@app.route('/scan/<size>/<int:num>')
def scan(size, num):

    if not is_logged_in():
        return redirect(url_for('login'))

    if is_away(size, num):
        return redirect(f"{url_for('checkin', size=size, num=num)}")

    return redirect(f"{url_for('checkout', size=size, num=num)}")


@app.route('/checkin/<size>/<int:num>', methods=['GET', 'POST'])
def checkin(size, num):
    """
    When the packet is away and is brought back
    """
    if not is_logged_in():
        return redirect(url_for('login'))

    cookie = ast.literal_eval(request.cookies.get(COOKIE))

    if request.method == "POST":
        on_checkin(size, num, cookie["first_name"], cookie["last_name"], request.form["location"])
        return redirect(url_for('confirm'))

    return render_template('checkin.html', url=request.url)


@app.route('/checkout/<size>/<int:num>', methods=['GET', 'POST'])
def checkout(size, num):
    """
    When the packet is taken away
    """
    if not is_logged_in():
        return redirect(url_for('login'))

    cookie = ast.literal_eval(request.cookies.get(COOKIE))

    on_checkout(size, num, cookie["first_name"], cookie["last_name"])
    return redirect(url_for('confirm'))


@app.route('/confirm')
def confirm():
    if not is_logged_in():
        return redirect(url_for('login'))

    return render_template('scan_confirm.html')


@app.route('/qr/<size>/<int:num>')
def qr(size, num):
    img = qrcode.make(f"{url_for('scan')}/{size}/{num}")
    image_io = BytesIO()
    img.save(image_io, 'PNG')
    image_io.seek(0)
    return send_file(
        image_io,
        as_attachment=False,
        mimetype='image/png'
    )


@app.route("/logout")
def logout():

    res = redirect('/')
    res.set_cookie(COOKIE, '', expires=0)
    return res

@app.route("/whereis/<size>/<num>")
def whereis(size, num):
    return get_status(size, num)


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


if __name__ == '__main__':
    app.run()


def is_logged_in():
    return COOKIE in request.cookies


def generate_cookie(first_name, last_name):
    return str({
        "first_name": first_name,
        "last_name": last_name
    })


# TODO lookup db
def is_user(first_name, last_name):
    data = (first_name, last_name)
    with app.app_context():
        records = get_db().execute("SELECT COUNT(1) from users WHERE first_name = ? AND last_name = ?", data).fetchone()

    return records[0] != 0


def get_status(size, num):
    data = (size, num)
    with app.app_context():
        return get_db().execute("SELECT status from boxes WHERE box_size=? AND box_num=?;", data).fetchone()[0]


def is_away(size, num):
    return get_status(size, num) == STATUS_AWAY


def on_checkin(size, num, first_name, last_name, status):
    data = (status, size, num)
    with app.app_context():
        get_db().execute("UPDATE boxes SET status=? WHERE box_size=? AND box_num=?;", data).connection.commit()

    log_move(size, num, first_name, last_name, status)


def on_checkout(size, num, first_name, last_name):
    data = (STATUS_AWAY, size, num)
    with app.app_context():
        get_db().execute("UPDATE boxes SET status=? WHERE box_size=? AND box_num=?;", data).connection.commit()

    log_move(size, num, first_name, last_name, STATUS_AWAY)


def log_move(size, num, first_name, last_name, status):
    data = (size, num, first_name, last_name, datetime.now(), status)
    with app.app_context():
        get_db().execute("INSERT INTO logs (box_size, box_num, first_name, last_name, timestamp, status) VALUES (?, ?, ?, ?, ?, ?)", data).connection.commit()

