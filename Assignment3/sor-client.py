'''
P3 SoR-Client
Chris Wong
V00780634
'''
import select
import socket
import sys
import time
import os
import re

OKREQUEST = 'HTTP/1.0 200 OK'
BADREQUEST = 'HTTP/1.0 400 Bad Request'
NOTFOUND = 'HTTP/1.0 404 Not Found'

sndBuf = []
rcvBuf = []

class Packet:
    def __init__(self, command, length, payload):
        self.command = command
        self.length = length
        self.payload = payload
        self.sequence = 0
        self.acknowledgment = 0
        self.window = 0

    # Packet to string
    def __str__(self):
        finalPacket = ''
        cmd = '|'.join(self.command) + '\r\n'
        seq = 'Sequence: ' + str(self.sequence) + '\r\n'
        l = 'Length: ' + str(self.length) + '\r\n'
        ack = 'Acknowledgment: ' + str(self.acknowledgment) + '\r\n'
        win = 'Window: ' + str(self.window) + '\r\n\r\n'
        finalPacket = cmd + seq + l + ack + win + self.payload
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
    def __init__(self, filePairs, bufSize, payloadLen):
        self.sequence = 0
        self.ack = -1
        self.state = 'close'
        self.serverSequence = 0
        self.serverAck = 0
        self.filePairs = filePairs
        self.curFileLen = 0
        self.fileBuffer = {}
        for pairs in self.filePairs:
            self.fileBuffer[pairs[1]] = ''
        self.currentFile = filePairs.pop(0)
        self.bufSize = int(bufSize)
        self.window = int(bufSize)
        self.payloadLen = payloadLen
        self.sentPackets = []
        self.lastValidAck = 0
        self.timer = 0

    # Sends requests, acks, fins
    def send(self, packet):
        # Fill packet with the correct values
        packet.sequence = self.sequence
        packet.acknowledgment = self.ack
        packet.window = self.window
        #self.sentPackets[self.sequence] = packet
        # Send the SYN
        if self.state == 'syn-sent':
            sndBuf.append(packet)
        # Send ACKs for data received
        elif self.state == 'connect':
            sndBuf.append(packet)
            self.sequence += packet.length
        # Send a FIN
        elif self.state == 'fin-sent':
            sndBuf.append(packet)
            self.sequence += 1
        self.sentPackets.insert(0, packet)
        
    # Receive packets
    def rcv(self, packet):
        self.timer = time.time()
        # Create new packet object and load values
        # from the text that was sent over
        p = Packet([], 0, '')
        p.unpack(packet)
        print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + 'Receive; ' + '|'.join(p.command) + '; Sequence: ' + str(p.sequence) + '; Length: ' + str(p.length) + '; Acknowledgement: ' + str(p.acknowledgment) + '; Window: ' + str(p.window)) 
        # Exit program if a reset was received
        if('RST' in p.command):
            sys.exit()
        # Send reset if packet size too big
        if int(p.length) > int(self.bufSize):
            self.sendRst()
            exit()
        # Received SYN reply, change state to connect
        self.lastValidAck = p.acknowledgment
        if self.state == 'syn-sent' and ('SYN' in p.command):
            self.ack += 1
            self.state = 'connect'
        # Ack received fin and close
        if self.state == 'fin-sent':
            ackPacket = Packet(['ACK'], 0, '')
            self.ack += 1
            self.send(ackPacket)
            self.state = 'done'
        # Receive data packets
        if self.state == 'connect':
            self.rcvData(p)

    # Deal with data packets
    def rcvData(self, packet):
        returnStaus = 200
        packetPayload = packet.payload
        self.ack += packet.length
        # Check if beggining of response
        lines = packetPayload.splitlines(keepends = True)
        for l in lines:
            # 200 OK
            if re.search(OKREQUEST, l, re.IGNORECASE):
                self.fileBuffer[self.currentFile[1]] = int(lines[2][16:])
                data = lines[4:]
                if os.path.isfile(self.currentFile[1]):
                    os.remove(self.currentFile[1])
                break
            # 404
            elif re.search(NOTFOUND, l, re.IGNORECASE):
                returnStaus = 404
                data = lines
            # Just data
            else:
                data = lines
        # Response OK
        if returnStaus == 200:
            # Write data to file
            f = open(self.currentFile[1], 'a')
            for d in data:
                f.write(d)
            f.flush()
            # Check if file current file is finished 
            if os.path.getsize(self.currentFile[1]) == self.fileBuffer[self.currentFile[1]]:
                f.close()
                # Check if there are more files to request
                if len(self.filePairs) > 0:
                    # Send ack and next request
                    self.currentFile = self.filePairs.pop(0)
                    nextRequestPayload = 'GET /' + self.currentFile[0] + ' HTTP/1.0\r\n'
                    nextRequestPayload += 'Connection: keep-alive\r\n\r\n'
                    nextRequest = Packet(['DAT','ACK'], len(nextRequestPayload), nextRequestPayload)
                    self.send(nextRequest)
                # No more files to request, send fin     
                else:
                    self.state = 'fin-sent'
                    finPacket = Packet(['ACK', 'FIN'], 0, '')
                    self.send(finPacket)
            # Send regular ack
            else:
                ackPacket = Packet(['ACK'], 0, '')
                self.send(ackPacket)
        # Server did not find requested file
        elif returnStaus == 404:
            # Check if there are more files to request
            if len(self.filePairs) > 0:
                # Send ack and next request
                self.currentFile = self.filePairs.pop(0)
                nextRequestPayload = 'GET /' + self.currentFile[0] + ' HTTP/1.0\r\n'
                nextRequestPayload += 'Connection: keep-alive\r\n\r\n'
                nextRequest = Packet(['DAT','ACK'], len(nextRequestPayload), nextRequestPayload)
                self.send(nextRequest)
            # No more files to request, send fin 
            else:
                self.state = 'fin-sent'
                finPacket = Packet(['ACK', 'FIN'], 0, '')
                self.send(finPacket)

    # Send Syn with first GET request
    def open(self, packet):
        self.state = 'syn-sent'
        self.send(packet)

    # Resend on timeout
    def timeout(self):
        sndBuf.append(self.sentPackets[0])
    
    # Send a reset packet
    def sendRst(self):
        packet = Packet(['RST'], 0, '')
        packet.sequence = self.sequence
        packet.acknowledgment = self.ack
        packet.window = self.window
        print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + 'Send; ' + '|'.join(packet.command) + '; Sequence: ' + str(packet.sequence) + '; Length: ' + str(packet.length) + '; Acknowledgement: ' + str(packet.acknowledgment) + '; Window: ' + str(packet.window)) 
        sndBuf.append(packet)

def main(argv):
    # Initial set up
    DEST = (sys.argv[1], int(sys.argv[2]))
    bufSize = sys.argv[3]
    payloadLen = sys.argv[4]
    fileList = sys.argv[5:]

    # Create list of files
    if(len(fileList) % 2 != 0):
        print('File Arguments Invalid')
        sys.exit()
    filePairs = [(fileList[i], fileList[i+1]) for i in range(0, len(fileList), 2)]
 
    # Create UDP socket
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Create RPD object
    rdp = RDP(filePairs, bufSize, payloadLen)

    # Send first request
    initialPayload = 'GET /' + rdp.currentFile[0] + ' HTTP/1.0\r\n'
    initialPayload += 'Connection: keep-alive\r\n\r\n'
    initialPacket = Packet(['SYN','DAT','ACK'], len(initialPayload), initialPayload)
    initialPacket.sequence = 0
    initialPacket.acknowledgment = -1
    initialPacket.window = bufSize
    rdp.open(initialPacket)
    rdp.timer = time.time()

    # Increase seq by data len and set ack to 0
    rdp.sequence += len(initialPayload) + 1
    rdp.ack = 0
    while True:
        readable, writable, exceptional = select.select([udp_sock], [udp_sock], [udp_sock])
        if udp_sock in readable:
            # Receive packet and send to RDP for processing
            rcvBuf.append(udp_sock.recv(2048).decode())
            message = rcvBuf.pop(0)
            rdp.window -= len(message)
            rdp.rcv(message)
            rdp.window += len(message)
        if udp_sock in writable:
            # Send packet to server
            if sndBuf:
                p = sndBuf.pop(0)
                message = p.__str__()
                print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + 'Send; ' + '|'.join(p.command) + '; Sequence: ' + str(p.sequence) + '; Length: ' + str(p.length) + '; Acknowledgement: ' + str(p.acknowledgment) + '; Window: ' + str(p.window))
                udp_sock.sendto(message.encode(), DEST)
            # Close the program if FIN handshake is done
            if rdp.state == 'done':
                sys.exit()
        # Timeout if not received in a while
        if (time.time() - rdp.timer > 0.3):
                rdp.timeout()
                rdp.timer = time.time()

if __name__ == "__main__":
    main(sys.argv[1:])