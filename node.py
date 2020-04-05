'''
A node runs on the user device and provide the secure  messaging
functionality.

Legend:
  Entities
    init - Initiator
    resp - Responder
  E2E pairing:  
    req - request
    rep - reply
    pub - public information (public keys of X3DH and rchpk_1)
'''
import pika
import shared
import keys
from time import sleep

class Node():

    def __init__(self, name, phone_number, contact_list):
        self.my_name = name
        self.my_cl = contact_list
                
        shared.deactivate_other_loggers()

        self.file_logger = shared.complete_logger(
            f'{self.my_name}_node', True)
        
        self.my_info = keys.NodeInfo(phone_number, self.file_logger)
        
        self.cu_logger = shared.chat_logger('you')
        
        self.register()

        # threads executing long lasting actions, such as listening on
        # queues or getting the user inputs
        self.helpers = [
            shared.QueueListener(
                f'{self.my_info.id}_rep_init_pub', self.rep_init_public),
            shared.QueueListener(
                f'{self.my_info.id}_rep_resp_pub', self.rep_resp_public),
            # collects the name of the selected user and returns it to
            # self.req_public together with the name of the queue where
            # to publish it 
            shared.InputThread(
                f'{self.my_info.id}_req_pub', self.req_public)
        ]

        # needed for encrypting messages
        self.sh = keys.SaltHelper(self.file_logger)
        
        self.print_contacts()
        
    
    def print_contacts(self):
        contact_strings = []
        max_str_len = 0

        for c in self.my_cl:
            contact_strings.append(f'{c}: {self.my_cl[c]}')
            if len(contact_strings[-1]) > max_str_len:
                max_str_len = len(contact_strings[-1])

        line_sep = '#' * (max_str_len + 4)
        print('\nContact list:')
        print(line_sep)

        for s in contact_strings:
            spaces = ' ' * (max_str_len - len(s))
            print(f'# {s}{spaces} #')

        print(line_sep)

        print('Enter the name of the contact you want'+\
                             ' to open a chat with: ')

        
    def register(self):
        shared.send_message('register', self.my_info.serialize())
        self.file_logger.info('Registration at server successful')

        
    def stop_incoming_chat_helper(self):
        info = 'Shutting down the device...'
        print(info)
        self.file_logger.info(info)

        for h in self.helpers:
            if h.queue == f'{self.my_info.id}_rep_resp_pub':
                h.stop()
                h.join()
                
        info = 'Device shut...'
        print(info)
        self.file_logger.info(info)

        
    def start_incoming_chat_helper(self):
        self.helpers.append(
            shared.QueueListener(
                f'{self.my_info.id}_rep_resp_pub', self.rep_resp_public)
        )
        info = 'Device on.'
        print(info)
        self.file_logger.info(info)


    def req_public(self, inp, queue_name):
        if inp in self.my_cl:
            self.file_logger.info(f'Sending message on {queue_name}')
            shared.send_message(queue_name, self.my_cl[inp])
        elif inp == '':
            pass
        # the next two branches simulate the case when a client shutdowns
        # and is unavailable to collect messages
        elif inp == 'shutDown()':
            self.stop_incoming_chat_helper()
        elif inp == 'switchOn()':
            self.start_incoming_chat_helper()
        else:
            print('Contact not found, please insert a valid contact name.')

            
    def id2name(self, id):
        for name, cid in self.my_cl.items():
            if cid == id:
                return name

            
    def rep_resp_public(self, ch, method, properties, resp_pub):
        self.file_logger.debug(resp_pub)
        resp_pub = keys.NodePublicInfo(resp_pub, self.file_logger)
        self.file_logger.debug(resp_pub)
        self.ou_logger = shared.chat_logger(self.id2name(resp_pub.id))
        self.file_logger.info(f'Receiving sender public keys: {resp_pub.id}')
        # start chat where the current user is the receiver and the
        # user whose public keys were received is the sender
        self.start_chat(resp_pub, is_initiator=False)


    def rep_init_public(self, ch, method, properties, init_pub):

        if init_pub != b'NotRegisteredError':
            init_pub = keys.NodePublicInfo(init_pub, self.file_logger)
            self.ou_logger = shared.chat_logger(self.id2name(init_pub.id))
            self.file_logger.info(f'Receiving receiver public keys: {init_pub}')
            # start chat where the current user is the sender and the
            # user whose public keys were received is the receiver
            self.start_chat(init_pub, is_initiator=True)
        else:
            self.cu_logger.info('Error: your friend is not registered')
            self.file_logger.info('Number not registered')


    def stop_contact_sel_helper(self):
        # stops the thread getting the input for contact selection
        for h in self.helpers:
            if type(h) is shared.InputThread:
                self.file_logger.info(f'Stopping selection thread, publishing on {h.queue}')
                h.stop() 
                self.helpers.remove(h)


    def compute_master_secret(self, oth_party_pub, is_initiator):
        # computing master secret
        if is_initiator:
            ms = self.my_info.compute_initiator_ms(
                oth_party_pub
            )

            # starts the asymmetric ratchet storing the first root
            # key in self.my_rch_keys

            self.my_info.compute_new_key(keys=['ek'])
            shared.send_message(
                f'{self.my_info.id}_update_initiator_epk',
                self.my_info.serialize(['ipk', 'prepk'])
            )

        else:
            ms = self.my_info.compute_responder_ms(oth_party_pub)

        # start asymmetric ratchet
        self.my_rch_keys = keys.RatchetKeys(ms, self.file_logger)

                
    def start_chat(self, oth_party_pub, is_initiator):
        '''
        Initiates the secure chat, allocating input/output handlers
        and computing the shared master secret.
        '''
        self.file_logger.info(f'{is_initiator} Setting X3DH master secret with my keys'+
                            f' {self.my_info}\nand other party keys {oth_party_pub}')

        ms = self.compute_master_secret(oth_party_pub, is_initiator)
        
        self.stop_contact_sel_helper()

        # starts the input thread
        resp_queue = f"{self.my_info.id}_to_{oth_party_pub.id}"
        self.helpers.append(
            shared.InputThread(
                resp_queue,
                self.on_message_sent,
                extra_args={'op_info': oth_party_pub}
            )
        )

        # queue from which  the current user gets messages
        init_queue = f"{oth_party_pub.id}_to_{self.my_info.id}"
        self.helpers.append(
            shared.QueueListener(init_queue,
                                 self.on_message_received,
                                 extra_args={'op_info': oth_party_pub})
        )
        

        print(f'Chat with {oth_party_pub.id} initialized. '+\
              'Press ENTER to start.')


    def marshal_message(self, msg):
        ct, nonce = self.my_rch_keys.encrypt(msg)#, cur_salt
        message = {
            'msg': ct,
            'nonce' : nonce,
            'rchpk' : self.my_rch_keys.rchk.public_key(),
            'j' :  self.my_rch_keys.j
        }
        mh = keys.MsgHolder(message, self.file_logger)
        self.file_logger.debug(f'MessageHolder ready to be sent: \n{mh}')
        return mh.serialize()
        
        
    def on_message_sent(self, inp, queue_name, op_info):
        # evaluate the keyboard input
        # get the TLS connection parameters
        cur_sym_ratchet = self.my_rch_keys.j
        if cur_sym_ratchet == 0:
            self.asymmetric_ratchet(op_info)
        # we have computed a symmetric ratchet, hence we increment
        # the counter
        
        if inp == 'exit()':
            self.terminate()
            return
        msg = self.marshal_message(inp)

        self.file_logger.info(f'Sending message to {queue_name}')
        self.cu_logger.info(inp)
        shared.send_message(queue_name, msg)

        
    def on_message_received(self, ch, method, properties, body, op_info):
        mh = keys.MsgHolder(body, self.file_logger)
        self.file_logger.debug(f'MessageHolder received: \n{mh}')

        if not self.my_rch_keys.is_equal_to_op_rchpk(mh.rchpk):
            self.asymmetric_ratchet(op_info, mh.rchpk)

        decrypted_body = self.my_rch_keys.\
            decrypt(mh.msg, mh.nonce).decode('utf-8')
        
        if decrypted_body == 'exit()':
            self.terminate()
            return
        
        self.ou_logger.info(decrypted_body)

        
    def asymmetric_ratchet(self, oth_party_pub, op_new_rchpk=None):
        if op_new_rchpk is None:
            # renew its ratchet key
            self.my_rch_keys.compute_new_key('rchk')
        else:
            # renew ratchet key of other party
            self.my_rch_keys.update_key('op_rchpk', op_new_rchpk)

        # zero the number of symmetric ratchets
        self.my_rch_keys.update_key('j', 0)
        self.my_rch_keys.new_asym_rchs(self.my_info, oth_party_pub)

        
    def terminate(self):
        for h in self.helpers:
            h.stop()
            if type(h) is shared.InputThread:
                shared.simulate_enter()
            else:
                h.join()
