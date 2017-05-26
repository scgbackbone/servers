import socket
try:
	from StringIO import StringIO
except ImportError:
	from io import StringIO
import sys
from datetime import datetime
import signal
import os
import errno


class WSGIServer(object):

	address_family = socket.AF_INET
	socket_type = socket.SOCK_STREAM
	request_queue_size = 10

	def __init__(self, server_address):
		# creating a listening socket 
		self.server_socket = server_socket = socket.socket(self.address_family, self.socket_type)
		server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # allow to reuse the same address
		server_socket.bind(server_address)  #bind
		server_socket.listen(self.request_queue_size) #activate
		host, port = self.server_socket.getsockname()[:2] # get host name and port 
		self.server_name = socket.getfqdn(host)
		self.server_port = port
		self.headers_set = []   #return headers set by web framework/web application 

	def set_app(self, application):
		self.application = application
		
	def serve_forever(self):
	    def zombie_killer(sig, frame):
	        while True:
	            try:
	                pid, status = os.waitpid(-1, os.WNOHANG)
	            except OSError:
	                return
	            if pid == 0: # no more zombie processes
	                return
	    server_socket = self.server_socket
	    signal.signal(signal.SIGCHLD, zombie_killer)
	    while True:
	        try:
	            self.client_connection, client_address = server_socket.accept()
	        except IOError as e:
	            code, msg = e.args
	            if code == errno.EINTR:
	                continue
	            else:
	                raise
	        pid = os.fork()
	        if pid == 0:  # child
	            server_socket.close()  # close child copy
	            self.handle_one_request() # handle one request and close the client connection - then wait for another connection
	            os._exit(0)
	        else:  # parent
	            self.client_connection.close()  # close parent copy

	def handle_one_request(self):
		self.request_data = request_data = self.client_connection.recv(1024).decode()
		# print formatted request a la 'curl -v'
		print("".join("< {line}\n".format(line=line) for line in request_data.splitlines()))
		self.parse_request(request_data)
		#construct environment dictionary using request data
		env = self.get_environ()
		# time to call our application callable and get back the result that will become HTTP response body
		result = self.application(env, self.start_response)
		# construct a response and send it back to the client
		self.finish_response(result)

	def parse_request(self, text):
		request_line = text.splitlines()[0]
		request_line = request_line.rstrip("\r\n")
		# break down the request line into components
		(self.request_method, #GET
		 self.path,           #/hello
		 self.request_version #HTTP/1.1
		 ) = request_line.split()

	def get_environ(self):
		env = {}
		# does not follow pep8 - study it !!!!
		# required WSGI variables
		env["wsgi.version"] = (1, 0)
		env["wsgi.url_scheme"] = "http"
		env["wsgi.input"] =  StringIO(self.request_data)
		env["wsgi.errors"] = sys.stderr
		env["wsgi.multithread"] = False
		env["wsgi.multiprocess"] = False
		env["wsgi.run_once"] = False
		# required CGI variables 
		env["REQUEST_METHOD"] = self.request_method
		env["PATH_INFO"] = self.path
		env["SERVER_NAME"] = self.server_name
		env["SERVER_PORT"] = str(self.server_port)
		return env

	def start_response(self, status, response_headers, exc_info=None):
		# add necessary server headers 
		dateANDtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		server_headers = [("Date", dateANDtime + " GMT+1"),("Server","WSGIServer 0.2")]
		self.headers_set = [status, response_headers + server_headers]
		# to adhere to WSGI specification the start_response must return a 'write' callable.
		# for simplicity's sake we'll ignore that detail for now 
		# return self.finish_response

	def finish_response(self, result):
		try:
			status, response_headers = self.headers_set
			response = "HTTP/1.1 {status}\r\n".format(status=status)
			for header in response_headers:
				response += "{0}: {1}\r\n".format(*header)
			response += "\r\n"
			for data in result:
				if type(data) != str:
					response += data.decode("utf-8")
				else: response += data
			# print formatted response data a la 'curl -v'
			print("".join("> {line}\n".format(line=line) for line in response.splitlines()))
			self.client_connection.sendall(response.encode())
		finally:
			self.client_connection.close()


SERVER_ADDRESS = (HOST, PORT) = "", 8888

def make_server(server_address, application):
	server = WSGIServer(server_address)
	server.set_app(application)
	return server


if __name__ == "__main__":
	if len(sys.argv) < 2:
		sys.exit("Provide a WSGI application object as module:callable")
	app_path = sys.argv[1]
	module, application = app_path.split(":")
	module = __import__(module)
	application = getattr(module, application)
	httpd = make_server(SERVER_ADDRESS, application)
	print("WSGIServer: Serving HTTP on port {port}...\n".format(port=PORT))
	httpd.serve_forever()
