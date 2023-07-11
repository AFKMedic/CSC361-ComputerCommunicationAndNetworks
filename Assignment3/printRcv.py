import socket
import sys

def main(argv):
    # Create UDP socket
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Try to bind to address
    try:
        udp_sock.bind(('localhost', 5000))
    except:
        print('Could not bind to address')
        sys.exit()

    while(True):
        print(udp_sock.recv(2048).decode())


if __name__ == "__main__":
    main(sys.argv[1:])