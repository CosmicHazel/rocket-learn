import os

import numpy as np

import torch
import torch.nn.functional as F

from rocket_learn.agent.pretrained_policy import HardcodedAgent
from rocket_learn.agent.pretrained_agents.nexto.nexto_obs import NextoObsBuilder

from rlgym.utils.gamestates import GameState


class Nexto(HardcodedAgent):
    def __init__(self, model_string, n_players):
        cur_dir = os.path.dirname(os.path.realpath(__file__))
        self.actor = torch.jit.load(os.path.join(cur_dir, model_string))
        self.obs_builder = NextoObsBuilder(n_players=n_players)
        self.previous_action = np.array([0, 0, 0, 0, 0, 0, 0, 0])
        self._lookup_table = self.make_lookup_table()
        self.state = None

    @staticmethod
    def make_lookup_table():
        actions = []
        # Ground
        for throttle in (-1, 0, 1):
            for steer in (-1, 0, 1):
                for boost in (0, 1):
                    for handbrake in (0, 1):
                        if boost == 1 and throttle != 1:
                            continue
                        actions.append([throttle or boost, steer, 0, steer, 0, 0, boost, handbrake])
        # Aerial
        for pitch in (-1, 0, 1):
            for yaw in (-1, 0, 1):
                for roll in (-1, 0, 1):
                    for jump in (0, 1):
                        for boost in (0, 1):
                            if jump == 1 and yaw != 0:  # Only need roll for sideflip
                                continue
                            if pitch == roll == jump == 0:  # Duplicate with ground
                                continue
                            # Enable handbrake for potential wavedashes
                            handbrake = jump == 1 and (pitch != 0 or yaw != 0 or roll != 0)
                            actions.append([boost, yaw, pitch, yaw, roll, jump, boost, handbrake])
        actions = np.array(actions)
        return actions

    def act(self, state: GameState, player_index: int):
        player = state.players[player_index]
        teammates = [p for p in state.players if p.team_num == player.team_num and p != player]
        opponents = [p for p in state.players if p.team_num != player.team_num]

        state.players = [player] + teammates + opponents

        self.obs_builder.reset(state)
        obs = self.obs_builder.build_obs(player, state, self.previous_action)

        obs = tuple(torch.from_numpy(s).float() for s in obs)

        with torch.no_grad():
            out = self.actor(obs)
        self.state = obs

        out = (out,)
        max_shape = max(o.shape[-1] for o in out)
        logits = torch.stack(
            [
                l
                if l.shape[-1] == max_shape
                else F.pad(l, pad=(0, max_shape - l.shape[-1]), value=float("-inf"))
                for l in out
            ],
            dim=1
        )

        actions = np.argmax(logits, axis=-1)


        # print(Categorical(logits=logits).sample())
        parsed = self._lookup_table[actions.item()]

        return parsed


