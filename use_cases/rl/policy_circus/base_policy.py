import torch


class BasePolicy:

    def __init__(self, id, policy_net):
        self.id = id
        self.policy_net = policy_net

    def get_action(self, state_tensor):
        """Base action selection"""
        with torch.no_grad():
            q_values = self.policy_net(state_tensor)
        return q_values.max(1).indices.item()
