#
# Created by Nathan Joosse
#

# Import required libraries
import paho.mqtt.client as mqtt
from datetime import datetime
from flask import Flask, flash, redirect, render_template, request, session, abort
import json
import os
import pandas as pd
import sqlite3
import time
from werkzeug.security import check_password_hash

# Bokeh libraries
import bokeh
from bokeh.embed import components
from bokeh.plotting import figure

app = Flask(__name__)

# Lookup table for the device names to locations where they are reporting from
deviceNameDict = {'DHT001': 'Office',
                  'DHT002': 'Kitchen',
                  'DHT003': 'Bedroom',
                  'DHT004': 'Undecided'}

def makePlot(df):
    dates = [datetime.strptime(x,"%Y-%m-%d %H:%M:%S") for x in df['datetime']]

    p = figure(plot_width=1500, plot_height=300, x_axis_type='datetime',
               x_axis_label='Time', y_axis_label='Temperature',
               title='Temperature chart')

    lineColours ={1:'red', 2:'orange', 3:'yellow', 4:'blue'}
    for ix in range(1, 5):
        data = df[df.device == deviceNameDict['DHT{:03d}'.format(ix)]]

        dates = [datetime.strptime(x,"%Y-%m-%d %H:%M:%S") for x in data['datetime']]

        dataSource = bokeh.models.ColumnDataSource(dict(xs=dates, ys=list(data.temperature)))

        p.xaxis.formatter = bokeh.models.formatters.DatetimeTickFormatter()

        p.line('xs','ys', color=lineColours[ix], legend_label='{} Temp'.format(deviceNameDict['DHT{:03d}'.format(ix)]), source=dataSource, line_width=2)

    return p

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("/esp8266/dhtreadings")

# The callback for when a PUBLISH message is received from the esp8266.
def on_message(client, userdata, message):
    if message.topic == "/esp8266/dhtreadings":
        print("["+time.asctime()+"] DHT readings update")
        dhtreadings_json = json.loads(message.payload)

        # connects to SQLite database. File is named "sensordata.db" without the quotes
        # WARNING: your database file should be in the same directory of the app.py file 
        #   or have the correct path
        conn=sqlite3.connect('sensordata.db')
        c=conn.cursor()

        c.execute("""INSERT INTO dhtreadings (datetime, temperature,
            humidity, device) VALUES(datetime('now'), (?), (?), (?))""", 
            (dhtreadings_json['temperature'],
            dhtreadings_json['humidity'], 
            deviceNameDict[dhtreadings_json['device']]))

        conn.commit()
        print("Inserted Record")
        conn.close()

# Starts the MQTT service that will listen for and read the data from the thermometers
mqttc=mqtt.Client()
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.username_pw_set('flask', 'waiter')
mqttc.connect("localhost",1883,60)
mqttc.loop_start()

# Handles the user login
@app.route('/login', methods=['POST'])
def do_admin_login():
    con = sqlite3.connect('sensordata.db')
    cur = con.cursor()
    cur.execute("SELECT password_hash FROM users WHERE username= ?", [request.form['username']])
    data = cur.fetchall()
    con.close()
    if len(data) > 0:
        if check_password_hash(data[0][0], request.form['password']):
            session['logged_in'] = True
    else:
        flash('wrong password!', 'error')
    return main()

# Logs the user out
@app.route("/logout")
def logout():
    session['logged_in'] = False
    return main()

# Reads the thermometer data from the database and draws the plot and table
@app.route('/thermometer')
def thermometerPage():
    if not session.get('logged_in'):
        return render_template('login.html')
    else:
        conn=sqlite3.connect('sensordata.db')
        readings = pd.read_sql_query("select id as id, temperature, humidity, datetime, date(datetime, 'localtime') as currentdate, time(datetime, 'localtime') as currenttime, device from dhtreadings where datetime > (SELECT DATETIME('now', '-7 day')) order by id desc", conn)
	plot = makePlot(readings)
        plotscript, plotdiv = components(plot)
        return render_template('thermometer.html', readings=readings, plotdiv = plotdiv, plotscript = plotscript)

@app.route("/")
def main():
    if not session.get('logged_in'):
        return render_template('login.html')
    else:
        return render_template('main.html')

@app.route("/attention")
def attentionButton():
    pass
    # render_template('attention.html')


if __name__ == "__main__":
    app.secret_key = os.urandom(12)
    app.run(host='0.0.0.0', port=8181, debug=True)
