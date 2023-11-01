from flask import Flask, request, abort
import os
import logging
import importlib

backend_name = os.environ['BACKEND']
backend_file_dict = {"TGI" : "tgi_backend", "OOBA" : "ooba_backend", "SD_AUTO" : "sd_auto_backend"}
backend_dict = {"TGI" : "TGIBackend", "OOBA" : "OOBABackend", "SD_AUTO" : "SDAUTOBackend"}
backend_lib = importlib.import_module(backend_file_dict[backend_name])
backend_class = getattr(backend_lib, backend_dict[backend_name])
flask_dict = getattr(backend_lib, "flask_dict")

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

print(f"server.py")

master_token = os.environ['MASTER_TOKEN']
container_id = os.environ['CONTAINER_ID']
control_server_url = os.environ['REPORT_ADDR']

backend = backend_class(container_id=container_id, master_token=master_token, control_server_url=control_server_url, send_data=True)

#################################################### CLIENT FACING ENDPOINTS ###########################################################################

@app.route('/<route>')
def handler(route):
    global backend
    flask_dict[route](backend, request)
    
#################################################### INTERNAL ENDPOINTS CALLED BY LOGWATCH #################################################################################################
@app.route('/report_capacity', methods=['POST'])
def report_capacity():
    global backend
    if ("mtoken" not in request.json.keys()) or not backend.check_master_token(request.json['mtoken']):
        abort(401)
    backend.metrics.report_batch_capacity(request.json)
    return "Reported capacity"

@app.route('/report_loaded', methods=['POST'])
def report_loaded():
    global backend
    if ("mtoken" not in request.json.keys()) or not backend.check_master_token(request.json['mtoken']):
        abort(401)
    backend.metrics.report_loaded(request.json)
    return "Reported loaded"

@app.route('/report_done', methods=['POST'])
def report_done():
    global backend
    if ("mtoken" not in request.json.keys()) or not backend.check_master_token(request.json['mtoken']):
        abort(401)
    backend.metrics.report_req_stats(request.json)
    return "Updated Metrics"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.environ['AUTH_PORT'], threaded=True)
