'''
P2
Chris Wong
V00780634
'''
import select
import socket
import sys
import re
import time

# REGEX
VALIDSYN = 'SYN\nSequence: [0-9]+\nLength: [0-9]+'
VALIDACK = 'ACK\nAcknowledgment: [0-9]+\nWindow: [0-9]+'
VALIDDAT = 'DAT\nSequence: [0-9]+\nLength: [0-9]+\n\n.*'
VALIDFIN = 'FIN\nSequence: [0-9]+\nLength: [0-9]+'
ACKNUM = '(?<=Acknowledgment: )[0-9]+'
WINDOWNUM = '(?<=Window: )[0-9]+'
SEQNUM = '(?<=Sequence: )[0-9]+'
LENNUM = '(?<=Length: )[0-9]+'
PKTCONTENT = '(?<=\n\n).*'

# Destination Info
DEST = ('localhost', 8887)

# Block Size
BLKSIZE = 1024

# Store packets before sending
file_buffer = []

# Dictionary for sent packets
# Use to resend lost packets
# Key is sequence number
# packet is removed if acked
sent_buffer = {}

# Stores packets for writing
wrt_buffer = {}

# Buffers for sending and receiving
snd_buffer = []
rcv_buffer = []

timeout = None

class packet:
    def __init__(self, command, length, data):
        self.command = command
        self.length = length
        self.data = data
        self.sequence = 0
    
    def getData(self):
        return self.data

    def getCommand(self):
        return self.command

    def getLength(self):
        return self.length

    def getSequence(self):
        return self.sequence
    
    def setSequence(self, sequence):
        self.sequence = sequence

class ack:
    def __init__(self, acknowledgment, window):
        self.command = 'ACK'
        self.acknowledgment = acknowledgment
        self.window = window
    
    def getCommand(self):
        return self.command

    def getAcknowledgment(self):
        return self.acknowledgment

    def getWindow(self):
        return self.window

    def setAcknowledgment(self, acknowledgment):
        self.acknowledgment = acknowledgment

    def setWindow(self, window):
        self.window = window

class rdp_sender:

    def __init__ (self):
        self.state = 'closed'
        self.lastAck = 0
        self.tripleDupe = 0
        self.window = 0
        self.sequence = 0
        self.timer = 0
    
    def send(self, key):
        if(len(file_buffer) == 0 and self.state == 'open'):
                self.state = 'fin-send'
        if self.state == 'syn-sent':
            message = packet('SYN', 0, '')
            self.timer = time.time()
            snd_buffer.append(message)
            sent_buffer[0] = message
        if self.state == 'open':
            if key == 0:
                if(self.window > 0):
                    if(file_buffer):
                        pkt = file_buffer.pop(0)
                        pkt.setSequence(self.sequence)
                        self.sequence = self.sequence + pkt.getLength()
                        snd_buffer.append(pkt)
                        sent_buffer[self.sequence] = pkt
            else:
                if(self.window > 0):
                    pkt = sent_buffer[key]
                    snd_buffer.append(pkt)
        if self.state == 'fin-send':
            self.close()

    def open(self):
        self.state = 'syn-sent'
        self.send(0)
    
    def rcv_ack(self, acknowledgment):
        ackno = re.search(ACKNUM, acknowledgment)
        window = re.search(WINDOWNUM, acknowledgment)
        self.timer = time.time()
        if self.state == 'syn-sent':
            if(int(ackno.group()) == 1):
                self.lastAck = int(ackno.group())
                self.sequence = self.lastAck
                self.window = int(window.group())
                self.state = 'open'
                self.send(0)
        if self.state == 'open':
            if(int(ackno.group()) <= self.lastAck):
                self.tripleDupe += 1
                self.window = int(window.group())
            if(self.tripleDupe >= 3):
                self.send(ackno.group())
            if(int(ackno.group()) == self.sequence):
                self.lastAck = int(ackno.group())
                self.window = int(window.group())
                self.send(0)
        if self.state == 'fin-sent':
            if(int(ackno.group()) == self.sequence + 1):
                quit()

    def timeout(self):
        if self.state == 'open' or self.state == 'syn-sent':
            self.send(self.sequence)
        else:
            self.close()

    def getTimer(self):
        return self.timer

    def setTimer(self, timer):
        self.timer = timer

    def close(self):
        pkt = packet('FIN', 0, '')
        pkt.setSequence(self.sequence)
        snd_buffer.append(pkt)
        sent_buffer[self.sequence] = pkt
        self.state = 'fin-sent'

class rdp_receiver:
    def __init__(self, writeFile):
        self.acked = 0
        self.windowSize = 2048
        self.writeFile = writeFile
        self.finPkt = 0

    def send_ack(self, acknowledgment):
        snd_buffer.append(acknowledgment)

    def rcv_data(self, message):
        
        if re.search(VALIDSYN, message):
            acknowledgment = ack(1, self.windowSize)
            self.acked = 1
            self.send_ack(acknowledgment)
        elif re.search(VALIDDAT, message):
            seq = re.search(SEQNUM, message)
            pkt_size = re.search(LENNUM, message)
            pkt_data = re.search(PKTCONTENT, message, re.S)
            acknowledgment = ack(self.acked, self.windowSize)
            if (int(seq.group()) == self.acked):
                wrt_buffer[int(self.acked)] = pkt_data.group()
                self.acked = self.acked + int(pkt_size.group())
                self.windowSize = self.windowSize - int(pkt_size.group())
                acknowledgment.setAcknowledgment(self.acked)
                acknowledgment.setWindow(self.windowSize)

            for key in wrt_buffer:
                with open(self.writeFile, 'a') as f:
                    f.write(wrt_buffer[key])
                self.windowSize += len(wrt_buffer[key])
            wrt_buffer.clear()
            acknowledgment.setWindow(self.windowSize)
            self.send_ack(acknowledgment)
        elif re.search(VALIDFIN, message):
            if(self.finPkt == 0):
                self.acked += 1
                self.finPkt = self.acked
                acknowledgment = ack(self.acked, self.windowSize)
                self.send_ack(acknowledgment)
            else:
                acknowledgment = ack(self.acked, self.windowSize)
                self.send_ack(acknowledgment)

def main(argv):
    # Initial set up for server
    host = sys.argv[1]
    port = sys.argv[2]
    readFile = sys.argv[3]
    writeFile = sys.argv[4]

    # Create UDP socket
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Try to bind server
    try:
        udp_sock.bind((host, int(port)))
    except:
        print('Could not bind to address')
        sys.exit()

    # Initiate classes
    sender = rdp_sender()
    receiver = rdp_receiver(writeFile)

    # Read in file and packetize contents
    with open(readFile, "rb") as f:
        counter = 0
        string = ''
        byte = f.read(1)
        while byte:
            # Do stuff with byte
            string += byte.decode()
            counter += 1
            if (counter % BLKSIZE) == 0:
                p = packet('DAT', len(string), string)
                file_buffer.append(p)
                string = ''
            byte = f.read(1)
        p = packet('DAT', len(string), string)
        file_buffer.append(p)

    # First SYN
    sender.open()
        
    while(True):
        readable, writable, exceptional = select.select([udp_sock], [udp_sock], [udp_sock], timeout)

        if udp_sock in readable:
            rcv_buffer.append(udp_sock.recv(2048).decode())
            message = rcv_buffer.pop(0)
            if(re.search(VALIDSYN, message)):
                print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + ': Receive; SYN; Sequence: 0; Length: 0')
                receiver.rcv_data(message)
            elif(re.search(VALIDACK, message)):
                ackno = re.search(ACKNUM, message)
                window = re.search(WINDOWNUM, message)
                print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + ': Receive; ACK; Acknowledgment:' + ackno.group() +  '; Window: ' + window.group())
                sender.rcv_ack(message)
            elif(re.search(VALIDDAT, message)):
                seqno = re.search(SEQNUM, message)
                lennum = re.search(LENNUM, message)
                print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + ': Receive; DAT; Sequence:' + seqno.group() +  '; Length: ' + lennum.group())
                receiver.rcv_data(message)
            elif(re.search(VALIDFIN, message)):
                ackno = re.search(ACKNUM, message)
                window = re.search(WINDOWNUM, message)
                print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + ': Receive; FIN; Sequence:' + seqno.group() +  '; Length: ' + lennum.group())
                receiver.rcv_data(message)
        
        if udp_sock in writable:
            if(snd_buffer):
                p = snd_buffer.pop(0)
                command = p.getCommand()
                if command == 'SYN':
                    message = p.getCommand() + '\nSequence: 0\nLength: 0\n'
                    udp_sock.sendto(message.encode(), DEST)
                    print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + ': Send; SYN; Sequence: 0; Length: 0')
                elif command == 'ACK':
                    message = p.getCommand() + '\nAcknowledgment: ' + str(p.getAcknowledgment()) + '\nWindow: ' + str(p.getWindow()) + '\n'
                    udp_sock.sendto(message.encode(), DEST)
                    print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + ': Send; ACK; Acknowledgment: ' + str(p.getAcknowledgment()) + '; Window: ' + str(p.getWindow()))
                elif command == 'DAT':
                    message = p.getCommand() + '\nSequence: ' + str(p.getSequence()) + '\nLength: ' + str(p.getLength()) + '\n\n' + p.getData()
                    udp_sock.sendto(message.encode(), DEST)
                    print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + ': Send; DAT; Sequence: ' + str(p.getSequence()) + '; Length: ' + str(p.getLength()))
                elif command == 'FIN':
                    message = p.getCommand() + '\nSequence: ' + str(p.getSequence()) + '\nLength: ' + str(p.getLength()) + '\n\n' + p.getData()
                    udp_sock.sendto(message.encode(), DEST)
                    print(time.strftime('%a %b %d %H:%M:%S %Z %Y: ') + ': Send; FIN; Sequence: ' + str(p.getSequence()) + '; Length: ' + str(p.getLength()))
                elif command == 'RST':
                    message = 'RST'
                    udp_sock.sendto(message.encode(), DEST)
            if (time.time() - sender.timer > 0.5):
                sender.timeout()
                sender.setTimer(time.time())


if __name__ == "__main__":
    main(sys.argv[1:])