from cryptography.hazmat.primitives.serialization \
    import Encoding, PublicFormat, load_der_public_key

import logging
import pika
import ssl
import threading
import functools
from pynput.keyboard import Key, Controller
from time import sleep


class QueueListener(threading.Thread):
    def __init__(self,  queue_name,
                 handler_function, logger=None,
                 over_tls=True, extra_args=None,
                 *args, **kwargs):
        super(QueueListener, self).__init__(*args, **kwargs)

        self.queue = queue_name
        self.handler = handler_function
        self.logger = logger
        self.over_tls = over_tls
        self.extra_args = extra_args
        self.start()

    def run(self):
        if self.over_tls:
            conn_params = get_tls_con_param()
        else:
            # TODO_IFF_TIME
            # conn_params = get_plain_con_param()
            pass

        with pika.BlockingConnection(conn_params) as self.conn:
            self.in_ch = self.conn.channel()

            # add extra arguments to the callback, if any
            if self.extra_args != None:
                self.handler = functools.partial(
                    self.handler, **self.extra_args
                )
                
            self.in_ch.queue_declare(self.queue)
            self.in_ch.basic_consume(
                queue=self.queue,
                on_message_callback=self.handler,
                auto_ack=True
            )
            # logger is not None only for the TTP's queueListeners
            if self.logger is not None:
                self.logger.info(
                    f' [*] Waiting for messages on {self.queue}'
                )

            self.in_ch.start_consuming()
            
    def kill(self):
        self.conn.close()

    def stop(self):
        self.conn.call_later(.5, self.kill)

class InputThread(threading.Thread):
    '''
    Thread used by nodes for users' inputs.
    '''
    
    def __init__(self, queue_name=None, input_cbk = None,
                 extra_args=None, name='keyboard-input-thread'):
        self.input_cbk = input_cbk
        self.queue = queue_name
        self.extra_args = extra_args
        super(InputThread, self).__init__(name=name)
        self.stopped = False
        self.start()

    def run(self):
        
        if self.extra_args != None:
            self.input_cbk = functools.partial(
                self.input_cbk, **self.extra_args
            )

        while not self.stopped:
            self.input_cbk(inp=input(), queue_name=self.queue)
            #waits to get input + Return

    def stop(self):
        self.stopped = True


def simulate_enter(is_initiator):
    keyboard = Controller()
    if not is_initiator:
        keyboard.press('c')
        keyboard.release('c')
        keyboard.press(Key.enter)
        keyboard.release(Key.enter)

    keyboard.press(Key.enter)
    keyboard.release(Key.enter)

def get_broker_cred():
    '''
    Fetches broker credentials from broker_authentication.sh used to
    set authentication credential on application startup.
    '''
    with open('broker_authentication.sh','r') as f:
        content = f.readlines()

    searched_info = ['export RMQ_USER=', 'export RMQ_PSW=']
    cred = []
    for l in content:
        for si in searched_info:
            if si in l:
                cred.append( l[len(si):].strip('\n') )
    return cred

def get_tls_con_param():
    '''
    Prepares the clients TLS connection parameters for the connection 
    to the server. 

    Here we use only one client certificate and authentication credentials,
    many of them should be 
    '''
    creds = get_broker_cred()

    context = ssl.create_default_context(
        cafile="./certs/ca_certificate.pem")
    context.load_cert_chain("./certs/client_certificate.pem",
                            "./certs/client_key.pem")
    ssl_options = pika.SSLOptions(context, "localhost")
    creds = pika.credentials.PlainCredentials(*creds)
    conn_params = pika.ConnectionParameters(port=5671,
                                            ssl_options=ssl_options,
                                            credentials=creds
    )
    return conn_params

def is_over_tls(conn_params):
    return conn_params.port == 5671

def send_message(queue_name, body, conn_params=get_tls_con_param()):
    '''
    Sends a message with payload specified by 'body' to queue 'queue_name'
    with plain or tls connection parameters. By default tls is used
    '''
    conn = pika.BlockingConnection(conn_params)
    out_ch = conn.channel()

    out_ch.queue_declare(queue_name)
    out_ch.basic_publish("", queue_name, body)
    if not is_over_tls(conn_params):
        # this is run when the secure signal
        # connection has been initialized
        print('[you]'+ body)
    
    
def serialize_pk(pk):
    '''
    Returns the serialized public key
    '''
    return pk.public_bytes(
        Encoding.X962,
        PublicFormat.CompressedPoint
    )


def deactivate_other_loggers():
    pikaLogger = logging.getLogger('pika')
    pikaLogger.setLevel('WARNING')

    
def chat_logger(loggerName):
    '''
    It configures a basic logging feature for the chat 
    '''
    

    logger = logging.getLogger(loggerName)
    stream_h = logging.StreamHandler()

    formatter = logging.Formatter(
        fmt='[%(name)s] >> %(message)s \n\t\t\t\t-- %(asctime)s',
        datefmt='%m/%d %H:%M:%S'
    )
    
    stream_h.setFormatter(formatter)
    logger.setLevel(logging.NOTSET)
    logger.addHandler(stream_h)
    
    return logger


def complete_logger(loggerName, inFile=False):
    '''
    It configures complex logging 
    '''

    FORMAT = '%(name)s| %(asctime)s [%(levelname)s] >> %(message)s'
    DATE_FORMAT = '%m-%d-%Y %H:%M:%S'
    
    if inFile:
        logging.basicConfig(filename=f'logs/{loggerName}.log',
                        filemode='w+', level=logging.NOTSET,
                        format=FORMAT, datefmt=DATE_FORMAT)
    
    else:
        logging.basicConfig(level=logging.NOTSET,
                        format=FORMAT,
                        datefmt=DATE_FORMAT)
    logger = logging.getLogger(loggerName)
    
        
    return logger

