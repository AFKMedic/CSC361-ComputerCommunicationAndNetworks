packets = {}

class packet:
    def __init__(self, command, length, data):
        self.command = command
        self.length = length
        self.data = data
    
    def getData(self):
        return self.data

    def getCommand(self):
        return self.command

    def getLength(self):
        return self.length

def main():
    
    with open("lorem.txt", "rb") as f:
        counter = 0
        string = ''
        byte = f.read(1)
        while byte:
            # Do stuff with byte
            string += byte.decode()
            counter += 1
            if (counter % 1024) == 0:
                #print(counter)
                p = packet('DATA', 'HEADER', string)
                packets[counter + 1] = p
                string = ''
            byte = f.read(1)
        p = packet('DATA', 'HEADER', string)
        packets[counter + 1] = p
        string = ''
        out = ''
        for key, value in packets.items():
            print(value.getData(), end='')

        

if __name__ == "__main__":
    main()