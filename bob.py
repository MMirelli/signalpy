import node 

if __name__ == "__main__":

    BOB_CONTACT_LIST = {
        'Alice': '+358 111 222 333',
        'Carol': '+358 333 111 222',
        'Eveline': '+358 123 123 123'
        }
    BOB_NAME = 'Bob'
    BOB_MOBILE = '+358 222 333 111'
    bob_node = node.Node(BOB_NAME, BOB_MOBILE, BOB_CONTACT_LIST)
