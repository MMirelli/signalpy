'''
Trusted Third Party (TTD) distributes identities to Nodes and executes 
bookeeping operations.
'''

import pika
import threading
import shared
import keys
from time import sleep

class TrustedThirdParty():

    def __init__(self):
        self.registered_users = []
        # deactivate other loggers
        shared.deactivate_other_loggers()
        self.logger = shared.complete_logger('TTP')
        
        self.queueListeners = [
            shared.QueueListener("register", self.register, self.logger)
        ]

        # SaltHelper generates the initial time-based seed,
        # which is assumed to be accessible to all users
        self.sh = keys.SaltHelper(self.logger)
        self.sh.generate_seed()

    def get_pub_if_registered(self, searched_id):
        i = 0
        rst = None
        while i < len(self.registered_users):
            if self.registered_users[i].id == searched_id:
                rst = self.registered_users[i]
            i += 1
        return rst

        
    def send_public(self, ch, method, properties, init_id, resp_pub):
                
        init_id = init_id.decode('utf-8')
        self.logger.info(f'New send public of {init_id} requested by {resp_pub.id}')
        init_pub = self.get_pub_if_registered(init_id)
        self.logger.debug(f'Info for id {init_id} are {init_pub}')
        self.logger.debug(f'Currently subscribed users: {self.registered_users}')
        # subscribe to channel to receive new ephemeral key
        self.queueListeners.append(
            shared.QueueListener(f"{resp_pub.id}_update_initiator_epk",
                                 self.update_epk, self.logger)
        )
        
        if init_pub is not None:
            msg_back_to_snd = init_pub.serialize(except_for=['epk'])

            shared.send_message(f'{init_id}_rep_resp_pub',
                                resp_pub.serialize(except_for=['prepk']))
        else:
            msg_back_to_snd = b'NotRegisteredError'
            
        shared.send_message(f'{resp_pub.id}_rep_init_pub', msg_back_to_snd)

        self.forget_epk(resp_pub.id)

    def log_registered_users(self):
        self.logger.info('All registered users:')
        for ru in self.registered_users:
            self.logger.info(ru)
        
    def update_epk(self, ch, method, properties, init_pub_new_eph_ser):
        init_pub_new_eph = keys.NodePublicInfo(
            init_pub_new_eph_ser,
            self.logger
        )
        self.logger.info(f'Updating ephemeral key {init_pub_new_eph.id}')
        stored_init_pub = self.get_pub_if_registered(init_pub_new_eph.id)
        stored_init_pub.union(init_pub_new_eph_ser)
        self.logger.info('Initiator updated pubs.')
        self.log_registered_users()

        
    def forget_epk(self, init_id):
        self.logger.info('Deleting ephemeral X3DH key of Initiator.')
        init_pub = self.get_pub_if_registered(init_id)
        init_pub.epk = None
        self.logger.info(f'Initiator pubs: {init_pub}')

        
    def register(self, ch, method, properties, cur_pub_info):
        # TODO_IFF_TIME: check user is unique and implement mechanism for
        # communicating errors 
        self.logger.debug(cur_pub_info)
        cur_pub_info = keys.NodePublicInfo(cur_pub_info, self.logger)
        self.logger.info("Registering user %r" % cur_pub_info.id)
        self.registered_users.append(cur_pub_info)
        
        cur_queue_list = shared.QueueListener(
            queue_name=f"{cur_pub_info.id}_req_pub",
            handler_function=self.send_public,
            logger=self.logger,
            over_tls=True,
            extra_args={'resp_pub': cur_pub_info})

        self.queueListeners.append(cur_queue_list)
        
if __name__ == "__main__":
    ttp = TrustedThirdParty()
        
