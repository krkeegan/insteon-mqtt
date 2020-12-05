import sys
import time
import subprocess
from shlex import split
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit


cli = sys.modules['flask.cli']
cli.show_server_banner = lambda *x: None
app = Flask(__name__, template_folder=".")
app.config['worker'] = None
app.config['cmd'] = []
socketio = SocketIO(app)

class Worker():
    '''
    This starts and stops the subprocess
    '''

    def __init__(self, sio, flask_app):
        """
        assign socketio object to emit
        """
        self.socketio = sio
        self.app = flask_app
        self.run = True

    def do_work(self):
        """
        do work and emit message
        """
        while self.run:
            if len(app.config['cmd']):
                command = self.app.config['cmd'].pop()
                socketio.emit('message', "\n\n>>>" + " ".join(command) + "\n")
                output = subprocess.Popen(command,
                                          text=True,
                                          stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT)
                line = output.stdout.readline()
                while line:
                    socketio.emit('message', line)
                    line = output.stdout.readline()
            else:
                time.sleep(.1)

    def stop(self):
        """
        stop the loop
        """
        self.run = False


@app.before_request
def before_request_func():
    if request.remote_addr != "172.30.32.2":
        return 'Unauthorized'
    return

@app.route('/')
def index():
    return render_template("index.html")

@socketio.on('message')
def handle_message(message):
    user_cmd = split(message)

    # Attempt to add some guardrails to prevent users from doing things
    # that would cause issues.
    if 'insteon-mqtt' in user_cmd[0].lower():
        emit('message', "!!!!!!! Error, the command prefix 'insteon-mqtt " +
             "config.yaml is automatically added to all commands.'\n")
    elif 'start' in user_cmd[0].lower():
        emit('message', "!!!!!!! Error, do not attempt to run the start " +
             "command from here, bad things would happen.'\n")
    elif 'stop' in user_cmd[0].lower():
        emit('message', "!!!!!!! Error, do not attempt to run the start " +
             "command from here, bad things would happen.'\n")
    elif 'config.yaml' in user_cmd[0].lower():
        emit('message', "!!!!!!! Error, the command prefix 'insteon-mqtt " +
             "config.yaml is automatically added to all commands.'\n")
    else:
        # If already defined, then skip
        if app.config["worker"] is None:
            app.config["worker"] = Worker(socketio, app)
            socketio.start_background_task(target=app.config["worker"].do_work)
        command = ['insteon-mqtt', '/config/insteon-mqtt/config.yaml']
        command.extend(user_cmd)
        app.config['cmd'].append(command)

@socketio.on('connect')
def test_connect():
    # If already defined, then skip
    if app.config["worker"]:
        return
    app.config["worker"] = Worker(socketio, app)
    socketio.start_background_task(target=app.config["worker"].do_work)

@socketio.on('estop')
def handle_estop(message):
    '''
    An emergency estop in case the process starts running away for some
    reason.  Stop the worker thread and reset the config states.
    '''
    if app.config["worker"]:
        app.config["worker"].stop()
        app.config["worker"] = None
        app.config['cmd'] = []

def start_webcli():
    socketio.run(app, host='0.0.0.0', port='8099')
