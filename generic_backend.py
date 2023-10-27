import secrets
from abc import ABC, abstractmethod
from auth import fetch_public_key, verify_signature
import json

NUM_AUTH_TOKENS = 1000
MSG_HISTORY_LEN = 100

class Backend(ABC):
    def __init__(self, container_id, control_server_url, master_token):
        self.curr_auth_tokens = set()
        self.num_auth_tokens = NUM_AUTH_TOKENS
        self.container_id = container_id
        self.control_server_url = control_server_url
        self.master_token = master_token
        self.reqnum = 0
        self.msg_history = []

        self.public_key = fetch_public_key()

    # def get_auth_tokens(self):
    #     new_token_batch = []
    #     for _ in range(self.num_auth_tokens):
    #         token = secrets.token_hex(32)
    #         new_token_batch.append(token)
    #     self.curr_auth_tokens |= set(new_token_batch)

    #     return new_token_batch

    def check_master_token(self, token):
        return token == self.master_token

    # def check_auth_token(self, token):
    #     if token in self.curr_auth_tokens:
    #         self.curr_auth_tokens.remove(token)
    #         return True
    #     elif token == self.master_token:
    #         return True
    #     else:
    #         return False

    def format_request(self, request):
        model_dict = {}
        model_dict.update(request)
        auth_names = ["signature", "endpoint", "reqnum", "url", "message"]
        has_auth = True
        for key in auth_names:
            if key not in request.keys():
                has_auth = False
            else:
                del model_dict[key]

        if has_auth:
            original_dict = {"cost" : request["cost"], "endpoint" : request["endpoint"], "reqnum" : request["reqnum"], "url" : request["url"]}
            message = json.dumps(original_dict, indent=4)
            auth_dict = {"signature" : request["signature"], "message": message, "reqnum" : request["reqnum"]}
        else:
            auth_dict = None
        
        return auth_dict, model_dict

    def check_signature(self, reqnum, message, signature):
        if reqnum < (self.reqnum - MSG_HISTORY_LEN):
            return False
        elif message in self.msg_history:
            return False
        elif verify_signature(self.public_key, message, signature):
            self.reqnum = max(reqnum, self.reqnum)
            self.msg_history.append(message)
            if len(self.msg_history) > MSG_HISTORY_LEN:
                self.msg_history = self.msg_history[len(self.msg_history) - MSG_HISTORY_LEN: ]
            return True
        else:
            return False

    def generate(self, model_request, endpoint):
        self.metrics.start_req(text_prompt=model_request["inputs"], parameters=model_request["parameters"])
        try:
            t1 = time.time()
            response = requests.post(f"http://{self.model_server_addr}/{endpoint}", json=model_request)
            t2 = time.time()
            self.metrics.finish_req(text_prompt=model_request["inputs"], parameters=model_request["parameters"])

            if response.status_code == 200:
                return 200, response.text, t2 - t1

            return response.status_code, None, None

        except requests.exceptions.RequestException as e:
            print(f"[backend] Request error: {e}")

        return 500, None, None

    @abstractmethod
    def generate_stream(self, model_request):
        pass
