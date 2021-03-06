import env_3
import agent_3
from config_3 import global_config as cfg
from message import message
import random
import torch
from torch.autograd import Variable
import numpy as np


def choose_start_facet(busi_id):
    choose_pool = list()
    if cfg.item_dict[str(busi_id)]['stars'] is not None:
        choose_pool.append('stars')
    if cfg.item_dict[str(busi_id)]['city'] is not None:
        choose_pool.append('city')
    if cfg.item_dict[str(busi_id)]['RestaurantsPriceRange2'] is not None:
        choose_pool.append('RestaurantsPriceRange2')

    #choose_pool.append('full_tag')
    #choose_pool += [cfg.tag_map_inverted[k] for k in cfg.item_dict[str(busi_id)]['categories']]  # add all feature name
    print('choose_pool is: {}'.format(choose_pool))

    THE_FEATURE = random.choice(choose_pool)

    return THE_FEATURE


def get_reward(history_list, gamma, trick, action_tracker, candidate_length_tracker):

    r_dict = {
        2: 1,
        1: 0.1,
        0: -0.1,
        -1: -0.1,
        -2: -0.3
    }

    reward_list = [r_dict[item] for item in history_list]

    action_tracker = [item[0] for item in action_tracker]
    rewards = []
    R = 0
    for r in reward_list[::-1]:
        R = r + gamma * R
        rewards.insert(0, R)

    # turn rewards to pytorch tensor and standardize
    rewards = torch.Tensor(rewards)

    # TODO: It is a trick, we can consider use it or not
    if trick == 1:
        rewards = (rewards - rewards.mean()) / (rewards.std() + np.finfo(np.float32).eps)

    return rewards

def run_one_episode(FM_model, user_id, busi_id, MAX_TURN, do_random, write_fp, strategy, TopKTaxo, PN_model, gamma, trick, mini, optimizer1_fm, optimizer2_fm, alwaysupdate, start_facet, sample_dict, choose_pool):
    # _______ initialize user and agent _______
    uncertainty = 0
    the_user = env_3.user(user_id, busi_id, uncertainty)

    log_prob_list, reward_list = Variable(torch.Tensor()), list()
    action_tracker, candidate_length_tracker = list(), list()

    epsilon = 1
    the_agent = agent_3.agent(FM_model, user_id, busi_id, do_random, write_fp, strategy, TopKTaxo, PN_model, log_prob_list, action_tracker, candidate_length_tracker, mini, optimizer1_fm, optimizer2_fm, alwaysupdate, epsilon, sample_dict, choose_pool)

    # _______ chat history _______
    chat_history = dict()

    # _______ initialize start message _______
    data = dict()
    data['facet'] = choose_start_facet(busi_id)
    data['itemID'] = busi_id
    #print('Starting facet is : {}'.format(data['facet']))
    start_signal = message(cfg.AGENT, cfg.USER, cfg.EPISODE_START, data)

    agent_utterance = None
    while(the_agent.turn_count < MAX_TURN):

        if the_agent.turn_count == 0:
            the_agent.bias = the_agent.cal_bias_at(start_signal.data['facet'])
            user_utterance = the_user.response(start_signal)
        else:
            user_utterance = the_user.response(agent_utterance)

        #print('The user utterance in #{} turn, type: {}, data: {}\n'.format(the_agent.turn_count, user_utterance.message_type, user_utterance.data))
        with open(write_fp, 'a') as f:
            f.write('The user utterance in #{} turn, type: {}, data: {}\n'.format(the_agent.turn_count, user_utterance.message_type, user_utterance.data))

        the_agent.turn_count += 1

        if (the_agent.turn_count == MAX_TURN or user_utterance.message_type == 'quit') and user_utterance.message_type != cfg.ACCEPT_REC:
            the_agent.history_list.append(-2)
            the_agent.response(user_utterance)
            print('Max turn quit...')
            rewards = get_reward(the_agent.history_list, gamma, trick, action_tracker, candidate_length_tracker)
            return the_agent.log_prob_list, rewards, the_agent.turn_count

        if user_utterance.message_type == cfg.ACCEPT_REC:
            the_agent.history_list.append(2)
            the_agent.response(user_utterance)
            cfg.turn_count[the_agent.turn_count] += 1
            print('Rec Success! in Turn: {}.'.format(the_agent.turn_count))
            rewards = get_reward(the_agent.history_list, gamma, trick, action_tracker, candidate_length_tracker)
            return the_agent.log_prob_list, rewards, the_agent.turn_count

        agent_utterance = the_agent.response(user_utterance)




def update_PN_model(model, log_prob_list, rewards, optimizer):
    model.train()
    if rewards is None:
        print('?')

    loss = torch.sum(torch.mul(log_prob_list, Variable(rewards)).mul(-1))

    optimizer.zero_grad()
    loss.backward()
    optimizer.step()