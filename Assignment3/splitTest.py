
string = 'SYN|ACK|DAT\r\nSequence: 0\r\nLength: 1024\r\nAcknowledgment: 49\r\nWindows: 4096\r\n\r\nGET /sws.py HTTP/1.0\r\nConnection: keep-alive\r\n'
split = string.splitlines(keepends=True)
command = split[0].rstrip()
seq = split[1]
length = split[2]
ack = split[3]
window = split[4]
#print(split)
#print(seq+length+ack+window)
#print(''.join(split[6:]))
#print(int(seq[10:]))
print(split[0].rstrip().split('|'))