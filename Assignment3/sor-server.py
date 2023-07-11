'''
P3 SoR-Server
Chris Wong
V00780634
'''
import select
import socket
import sys
import re
import time
import os #file_size = os.path.getsize

REFILENAME = ' /.* '
VALIDGET = '^GET \/.* HTTP\/1.0[\r|\n]'
VALIDPERS = '^connection: keep-alive[\r|\n]'
sndBuf = []
rcvBuf = {}
activeConnections = {}

class Packet:  
    def __init__(self, command, length, payload):
        self.command = command
        self.length = length
        self.payload = payload
        self.window = 0
        self.acknowledgment = -1
        self.sequence = 0

    # Packet to string
    def __str__(self):
        finalPacket = ''
        printCmd = '|'.join(self.command) + '\r\n'
        printSeq = 'Sequence: ' + str(self.sequence) + '\r\n'
        printLen = 'Length: ' + str(self.length) + '\r\n'
        printAck = 'Acknowledgment: ' + str(self.acknowledgment) + '\r\n'
        printWin = 'Window: ' + str(self.window) + '\r\n\r\n'
        finalPacket = printCmd + printSeq + printLen + printAck + printWin + self.payload
        return finalPacket

    # String to packet
    def unpack(self, packet):
        split = packet.splitlines(keepends=True)
        self.command = split[0].rstrip().split('|')
        self.sequence = int(split[1][10:])
        self.length = int(split[2][8:])
        self.acknowledgment = int(split[3][16:])
        self.window = int(split[4][8:])
        self.payload = ''.join(split[6:])


class RDP:
    def __init__(self, destination, bufferSize, window, payloadSize):
        self.sequence = 0
        self.ack = -1
        self.state = 'close'
        self.fileName = ''
        self.bufferSize = bufferSize
        self.window = window
        self.payloadSize = payloadSize
        self.clientSequence = 0
        self.clientAck = 0
        self.clientWindow = 0
        self.clientDest = destination
        self.sndPacket = Packet([], 0, '')
        self.fileBuffer = []
        self.sentPackets = []
        self.lastReceivedAck = -1
        self.timer = 0
        self.retries = 0

    def rcv(self, packet):
        # Create new packet object and load data from received packet
        p = Packet([], 0, '')
        p.unpack(packet)
        self.retries = 0
        # Received a RST
        if 'RST' in p.command:
            self.state == 'done'
            return
        # Drop packet if ack lower than sequenece
        if p.acknowledgment < self.lastReceivedAck:
            return
        self.lastReceivedAck = p.acknowledgment
        if not self.sequence == self.lastReceivedAck and not self.sequence == 0:
            self.resend()
            return
        # Send reset if packet size too big
        if int(p.length) > int(self.bufferSize):
            self.sendRst()
        if 'FIN' in p.command:
            self.state = 'fin-rcv'
        if self.state == 'connect':
            # RCV ACK FROM SENT DATA
            # Check ack number
            if 'DAT' in p.command and 'ACK' in p.command:
                self.rcvData(p)
            elif 'ACK' in p.command:
                if(len(self.fileBuffer) > 0):
                    payload = self.fileBuffer.pop(0)
                self.sndPacket = Packet(['ACK', 'DAT'], len(payload), payload)
                self.send()
        if self.state == 'fin-rcv':
            # SEND ACK|FIN
            self.sndPacket.command = ['ACK', 'FIN']
            self.sndPacket.payload = ''
            self.ack += 1
            self.sequence += 1
            self.send()
        if self.state == 'fin-sent':
            # Get ack and close or timeout and close
            self.state = 'done'
        if self.state == 'close':
            if 'SYN' in p.command:
                self.state = 'syn-rcv'
                self.timer = time.time()
                self.rcvSyn(p)

    def send(self):
        self.sndPacket.length = len(self.sndPacket.payload)
        self.sndPacket.acknowledgment = self.ack
        self.sndPacket.window = self.window
        self.sndPacket.sequence = self.sequence
        self.sequence += self.sndPacket.length
        if self.state == 'syn-rcv':
            pass
        elif self.state == 'connect':
            sndBuf.append((self.sndPacket, self.clientDest))
        elif self.state == 'fin-rcv':
            # Build ACK|FIN packet and send
            sndBuf.append((self.sndPacket, self.clientDest))
            self.state = 'fin-sent'
        self.sentPackets.insert(0, self.sndPacket)
                
    # Send a reset packet
    def sendRst(self):
        packet = Packet(['RST'], 0, '')
        packet.sequence = self.sequence
        packet.acknowledgment = self.ack
        packet.window = self.window
        sndBuf.append((packet, self.clientDest))

    def rcvSyn(self, packet):
        self.sequence = 0
        # Update own values
        self.clientSequence = packet.sequence
        self.clientAck = packet.acknowledgment
        self.clientWindow = packet.window
        self.ack = 1
        self.sequence += 1
        # Update to sndPacket
        self.sndPacket.command.append('SYN')
        self.sndPacket.command.append('ACK')
        self.sndPacket.acknowledgment = 1
        self.ack += packet.length
        if('DAT' in packet.command):
            self.rcvData(packet)
        else:
            self.send()

    def rcvData(self, packet):
        # Receive GET request
        # Clear previous payloads
        self.sndPacket.payload = ''
        # Get filename
        lines = packet.payload.splitlines(keepends=True)
        regexObj = re.search(REFILENAME, lines[0])
        fileName = regexObj.group()
        fileName = fileName.strip()
        fileName = fileName[1:]
        # Check if valid GET request
        # If invalid send reset
        if not re.search(VALIDGET, lines[0]):
            print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + str(self.clientDest[0]) + ':' + str(self.clientDest[1]) + ' ' + lines[0].strip() + '; HTTP/1.0 400 Bad Request')
            self.sendRst()
            return
        if lines[2] == '/\r/\n' or lines[2] == '/\n':
            if not re.search(VALIDGET, lines[1], re.IGNORECASE):
                self.sendRst()
                return
        # Try to get size of file on disk
        # Send back 404 on exception
        try:
            fileSize = os.path.getsize(fileName)
            print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + str(self.clientDest[0]) + ':' + str(self.clientDest[1]) + ' ' + lines[0].strip() + '; HTTP/1.0 200 OK')
        except:
            # Send 404 message here
            notFoundHTTP = 'HTTP/1.0 404 Not Found\r\nConnection: keep-alive\r\n'
            if('SYN' in self.sndPacket.command):
                self.sndPacket.command.append('DAT')
                self.state = 'connect'
            else:
                self.sndPacket.command = ['ACK', 'DAT']
            self.sndPacket.payload = notFoundHTTP
            print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + str(self.clientDest[0]) + ':' + str(self.clientDest[1]) + ' ' + lines[0].strip() + '; HTTP/1.0 404 Not Found')
            self.send()
            return
        # Set up response
        okHTTP = 'HTTP/1.0 200 OK\r\n'
        okHTTP += 'Connection: keep-alive\r\n'
        okHTTP += 'Content-Length: ' + str(fileSize) + '\r\n\r\n'
        if not ('DAT' in self.sndPacket.command):
            self.sndPacket.command.append('DAT')
        self.sndPacket.payload += okHTTP
        self.sndPacket.acknowledgment = packet.length + 1
        # Read file contents into first response packet
        # Read remaining file contents into file buffer
        openFile = open(fileName)
        data = openFile.read(self.payloadSize - len(okHTTP))
        #self.sndPacket.payload += data
        self.fileBuffer.append(okHTTP + data)
        while(True):
            fileRead = openFile.read(self.payloadSize)
            if(fileRead == ''):
                break
            self.fileBuffer.append(fileRead)
        # Update own values
        self.state = 'connect'
        self.send()

    def timeout(self):
        self.retries += 1
        if self.retries > 3:
            self.state = 'done'
            return
        if self.state == 'conenct' or self.state == 'syn-sent':
            self.resend()
        elif self.state == 'fin-sent':
            self.state = 'done'

    def resend(self):
        sndBuf.append((self.sentPackets[0], self.clientDest))

def main(argv):
    # Initial set up
    host = sys.argv[1]
    port = sys.argv[2]
    bufferSize = sys.argv[3]
    window = sys.argv[3]
    payloadSize = sys.argv[4]

    # Create UDP socket
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Try to bind to address
    try:
        udp_sock.bind((host, int(port)))
    except:
        print('Could not bind to address')
        sys.exit()

    while(True):
        readable, writable, exceptional = select.select([udp_sock], [udp_sock], [udp_sock])

        # Check for finished connections and remove
        # them from the active connections list
        rmvList = []
        for key in activeConnections:
            if activeConnections[key].state == 'done':
                    rmvList.append(key)
        if len(rmvList) > 0:
            for key in rmvList:
                del activeConnections[key]

        if udp_sock in readable:
            receivedData = udp_sock.recvfrom(2048)
            packet = receivedData[0].decode()
            address = receivedData[1]
            # Process with existing RDP instance or
            # assign new RDP instance to connection into activeConnections
            if address in activeConnections:
                activeConnections[address].rcv(packet)
            else: 
                activeConnections[address] = RDP(address, int(bufferSize), int(window), int(payloadSize))
                activeConnections[address].rcv(packet)

        if udp_sock in writable:
            if(sndBuf):
                outgoing = sndBuf.pop(0)
                p = outgoing[0]
                dest = outgoing[1]
                udp_sock.sendto(p.__str__().encode(), dest)
                # Remove from active connections if a reset is sent
                if('RST' in p.command):
                    activeConnections.pop(dest)
                if len(activeConnections) > 0:
                    for dest in activeConnections:
                        if (time.time() - activeConnections[dest].timer > 0.3):
                            activeConnections[dest].timeout()
                            activeConnections[dest].timer = time.time()

if __name__ == "__main__":
    main(sys.argv[1:])