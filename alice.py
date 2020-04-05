import node 

if __name__ == "__main__":
    
    ALICE_CONTACT_LIST = {
        'Bob': '+358 222 333 111',
        'Carol': '+358 333 111 222',
        'Dave': '+358 123 123 123'
    }
    ALICE_NAME = 'Alice'
    ALICE_MOBILE = '+358 111 222 333'
    alice_node = node.Node(ALICE_NAME, ALICE_MOBILE, ALICE_CONTACT_LIST)
