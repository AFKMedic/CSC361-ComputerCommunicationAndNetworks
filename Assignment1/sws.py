'''
P1
Chris Wong
V00780634
'''
import select
import socket
import sys
import queue
import time
import re

# Server Socket
server = None

# Readable Sockets
inputs = []

# Writable Sockets
outputs = []

# Outgoing queue
response_messages = {}

# Request messages
request_message = {}

# Request time
request_time = {}

# Request Persistency
request_pers = {}

# Regex
BADREQUESTMESSAGE = 'HTTP/1.0 400 Bad Request\r\n'
REFILENAME = ' /.* '
VALIDGET = '^GET \/.* HTTP\/1.0[\r|\n]'
VALIDCLOSE = '^connection: close[\r|\n]'
VALIDPERS = '^connection: keep-alive[\r|\n]'
VALIDEND = '^[\n\n|\r\n\r\n]'
VALIDREQEND = '^[\n\n|\r\n\r\n]$'

def main(argv):
    #Initial set up for server
    host = sys.argv[1]
    port = sys.argv[2]

    # Create socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Set non-blocking
    server.setblocking(0)

    # Try to bind server
    try:
        server.bind((host, int(port)))
    except:
        print('Could not bind to address')
        sys.exit()

    # Listen for requests
    server.listen(5)

    # Readable Sockets
    inputs.append(server)

    while True:
        # Wait for at least one of the sockets to be ready for processing
        readable, writable, exceptional = select.select(inputs, outputs, inputs)

        for s in readable:
            if s == server:
                new_connection(s)
            else:
                #Receive message from the receiving buffer
                existing_connection(s)

        for s in writable :
            send_reponse(s)

        for s in exceptional:
            handle_exceptional(s)

def new_connection(s):
    #accept new connection, and append new connection socket to the list to watch for readability
    c, a = s.accept()
    inputs.append(c)
    response_messages[c] = queue.Queue()
    # Add time of connection to check for timeouts
    request_time[c] = time.time()
    return

def existing_connection(s):
    # Watch for timeout of 60 seconds before recv
    if(time.time() - request_time.get(s) > 60.0):
        s.close()
        inputs.remove(s)
        return
    message = s.recv(1024).decode()
    sockName = s.getsockname()
    if message:
        # Update Timeout if a message was recieved
        request_time[s] = time.time()
        if s in request_message:
            request_message[s] = request_message[s] + message
        else:
            request_message[s] = message
        if re.search(VALIDREQEND, message, re.MULTILINE):
            whole_message = request_message[s]
            if s not in outputs:
                outputs.append(s)

            tmpFileBuf = ''
            getFlag = False
            
            # Process request line by line
            for line in whole_message.splitlines(keepends=True):
                # Handle headers
                if (re.search(VALIDPERS, line, re.IGNORECASE) or re.search(VALIDCLOSE, line ,re.IGNORECASE)) and getFlag == True:
                    response_messages[s].put(line)
                    response_messages[s].put(tmpFileBuf)
                    getFlag = False
                    if re.search(VALIDPERS, line, re.IGNORECASE):
                        request_pers[s] = True
                elif(getFlag):
                    response_messages[s].put(tmpFileBuf)
                    getFlag = False
                    
                # Handle GET line
                if re.search(VALIDGET, line):
                    getFlag = True
                    regexObj = re.search(REFILENAME, line)
                    filename = regexObj.group()
                    filename = filename.strip()
                    filename = filename[1:]
                    # Attempt to open the file
                    try:
                        getReq = ''
                        getReq = line.strip()
                        f = open(filename, 'r')
                        tmpFileBuf = f.read()
                        response_messages[s].put('HTTP/1.0 200 OK\n')
                        print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + str(sockName[0]) + ':' + str(sockName[1]) + ' ' + getReq + '; HTTP/1.0 200 OK')
                        f.close()
                    # Give 404 if the file cannot be opened
                    except:
                        response_messages[s].put('HTTP/1.0 404 Not Found\n')
                        print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + str(sockName[0]) + ':' + str(sockName[1]) + ' ' + getReq + '; HTTP/1.0 404 Not Found')
                # Handle end of request
                if re.search(VALIDEND, line):
                    response_messages[s].put(line)

                # Handle bad request
                if not (re.search(VALIDGET, line) or re.search(VALIDPERS, line, re.IGNORECASE) or re.search(VALIDCLOSE, line, re.IGNORECASE) or re.search(VALIDEND, line)):
                    response_messages[s].put(BADREQUESTMESSAGE)
                    response_messages[s].put('Connection: Closed')
                    print(time.ctime() + ': ' + str(sockName[0]) + ':' + str(sockName[1]) + ' HTTP/1.0 400 Bad Request')
                    if s in request_pers:
                        request_pers.pop(s)
                    break
    return

def send_reponse(s):
    # Get next message in response queue
    try:
        next_msg = response_messages[s].get_nowait()

    except queue.Empty:
        # Handle persistent connection
        if s in request_pers:
            outputs.remove(s)
            request_pers.pop(s)
        # Handle non persistent connection
        else:
            s.close()
            if s in inputs:
                inputs.remove(s)
            if s in outputs:
                outputs.remove(s)
            if s in request_pers:
                request_pers.pop(s)
        request_message.pop(s)
    else:
        # Send response
        s.send(next_msg.encode())
    return

def handle_exceptional(s):
    s.close()
    if s in inputs:
        inputs.remove(s)
    if s in outputs:
        outputs.remove(s)
    if s in request_message:
        request_message.pop(s)
    if s in request_pers(s):
        request_pers.pop(s)
    return

if __name__ == "__main__":
    main(sys.argv[1:])