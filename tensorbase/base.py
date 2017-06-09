#!/usr/bin/env python

"""
@author: Dan Salo, Nov 2016
Purpose: To facilitate data I/O, and model training in TensorFlow
Classes:
    Data
    Model
"""

import tensorflow as tf
import numpy as np
import logging
import math
import os

from tensorflow.python import pywrap_tensorflow
import sys

class Data:
    """
    A Class to handle data I/O and batching in TensorFlow.
    Use class methods for datasets:
        - That can be loaded into memory all at once.
        - That use the placeholder function in TensorFlow
    Use batch_inputs method et al for datasets:
        - That can't be loaded into memory all at once.
        - That use queueing and threading fuctions in TesnorFlow
    """

    def __init__(self, flags, valid_percent=0.2, test_percent=0.15):
        self.flags = flags
        train_images, train_labels, self.test_images, self.test_labels = self.load_data(test_percent)
        self._num_test_images = len(self.test_labels)
        self._num_train_images = math.floor(len(train_labels) * (1 - valid_percent))
        self._num_valid_images = len(train_labels) - self._num_train_images
        self.train_images, self.train_labels, self.valid_images, self.valid_labels = \
            self.split_data(train_images, train_labels)

        self.train_epochs_completed = 0
        self.index_in_train_epoch = 0
        self.index_in_valid_epoch = 0
        self.index_in_test_epoch = 0

    def load_data(self, test_percent=0.15):
        """Load the dataset into memory. If data is not divided into train/test, use test_percent to divide the data"""
        train_images = list()
        train_labels = list()
        test_images = list()
        test_labels = list()
        return train_images, train_labels, test_images, test_labels

    def split_data(self, train_images, train_labels):
        """
        :param train_images: numpy array (image_dim, image_dim, num_images)
        :param train_labels: numpy array (labels)
        :return: train_images, train_labels, valid_images, valid_labels
        """
        valid_images = train_images[:self.num_valid_images]
        valid_labels = train_labels[:self.num_valid_images]
        train_images = train_images[self.num_valid_images:]
        train_labels = train_labels[self.num_valid_images:]
        return train_images, train_labels, valid_images, valid_labels

    def next_train_batch(self, batch_size):
        """
        Return the next batch of examples from train data set
        :param batch_size: int, size of image batch returned
        :return train_labels: list, of labels
        :return images: list, of images
        """
        start = self.index_in_train_epoch
        self.index_in_train_epoch += batch_size
        if self.index_in_train_epoch > self.num_train_images:
            # Finished epoch
            self.train_epochs_completed += 1

            # Shuffle the data
            perm = np.arange(self.num_train_images)
            np.random.shuffle(perm)
            self.train_images = self.train_images[perm]
            self.train_labels = self.train_labels[perm]

            # Start next epoch
            start = 0
            self.index_in_train_epoch = batch_size
            assert batch_size <= self.num_train_images

        end = self.index_in_train_epoch
        return self.train_labels[start:end], self.img_norm(self.train_images[start:end])

    def next_valid_batch(self, batch_size):
        """
        Return the next batch of examples from validiation data set
        :param batch_size: int, size of image batch returned
        :return train_labels: list, of labels
        :return images: list, of images
        """
        start = self.index_in_valid_epoch
        if self.index_in_valid_epoch + batch_size > self.num_valid_images:
            batch_size = 1
        self.index_in_valid_epoch += batch_size
        end = self.index_in_valid_epoch
        return self.valid_labels[start:end], self.img_norm(self.valid_images[start:end]), end, batch_size

    def next_test_batch(self, batch_size):
        """
        Return the next batch of examples from test data set
        :param batch_size: int, size of image batch returned
        :return train_labels: list, of labels
        :return images: list, of images
        """
        start = self.index_in_test_epoch
        print(start)
        if self.index_in_test_epoch + batch_size > self.num_test_images:
            batch_size = 1
        self.index_in_test_epoch += batch_size
        end = self.index_in_test_epoch
        return self.test_labels[start:end], self.img_norm(self.test_images[start:end]), end, batch_size

    @property
    def num_train_images(self):
        return self._num_train_images

    @property
    def num_test_images(self):
        return self._num_test_images

    @property
    def num_valid_images(self):
        return self._num_valid_images

    @staticmethod
    def img_norm(x, max_val=255):
        """
        Normalizes stack of images
        :param x: input feature map stack, assume uint8
        :param max_val: int, maximum value of input tensor
        :return: output feature map stack
        """
        return (x * (1 / max_val) - 0.5) * 2  # returns scaled input ranging from [-1, 1]

    @classmethod
    def batch_inputs(cls, read_and_decode_fn, tf_file, batch_size, mode="train", num_readers=4, num_threads=4,
                     min_examples=1000):
        with tf.name_scope('batch_processing'):
            example_serialized = cls.queue_setup(tf_file, mode, batch_size, num_readers, min_examples)
            decoded_data = cls.thread_setup(read_and_decode_fn, example_serialized, num_threads)
            return tf.train.batch_join(decoded_data, batch_size=batch_size)

    @staticmethod
    def queue_setup(filename, mode, batch_size, num_readers, min_examples):
        """ Sets up the queue runners for data input """
        filename_queue = tf.train.string_input_producer([filename], shuffle=True, capacity=16)
        if mode == "train":
            examples_queue = tf.RandomShuffleQueue(capacity=min_examples + 3 * batch_size,
                                                   min_after_dequeue=min_examples, dtypes=[tf.string])
        else:
            examples_queue = tf.FIFOQueue(capacity=min_examples + 3 * batch_size, dtypes=[tf.string])
        enqueue_ops = list()
        for _ in range(num_readers):
            reader = tf.TFRecordReader()
            _, value = reader.read(filename_queue)
            enqueue_ops.append(examples_queue.enqueue([value]))
        tf.train.queue_runner.add_queue_runner(tf.train.queue_runner.QueueRunner(examples_queue, enqueue_ops))
        example_serialized = examples_queue.dequeue()
        return example_serialized

    @staticmethod
    def thread_setup(read_and_decode_fn, example_serialized, num_threads):
        """ Sets up the threads within each reader """
        decoded_data = list()
        for _ in range(num_threads):
            decoded_data.append(read_and_decode_fn(example_serialized))
        return decoded_data

    @staticmethod
    def init_threads(tf_session):
        """ Starts threads running """
        coord = tf.train.Coordinator()
        threads = list()
        for qr in tf.get_collection(tf.GraphKeys.QUEUE_RUNNERS):
            threads.extend(qr.create_threads(tf_session, coord=coord, daemon=True, start=True))
        return threads, coord

    @staticmethod
    def exit_threads(threads, coord):
        """ Closes out all threads """
        coord.request_stop()
        coord.join(threads, stop_grace_period_secs=10)


class Model:
    """
    A Class for easy Model Training.
    Methods:
        See list in __init__() function
    """

    def __init__(self, flags, config_dict=None):
        config_yaml_flags_dict = self.load_config_yaml(flags, config_dict)
        config_yaml_flags_dict_none = self.check_dict_keys(config_yaml_flags_dict)

        # Define constants
        self.step = 1
        self.flags = config_yaml_flags_dict_none

        # Run initialization functions
        self._check_file_io()
        self._data()
        self._set_seed()
        self._network()
        self._optimizer()
        self._summaries()
        self.merged, self.saver, self.sess, self.writer = self._set_tf_functions()
        self._initialize_model()

    def load_config_yaml(self, flags, config_dict):
        """ Load config dict and yaml dict and then override both with flags dict. """
        if config_dict is None:
            print('Config File not specified. Using only input flags.')
            return flags
        try:
            config_yaml_dict = self.cfg_from_file(flags['YAML_FILE'], config_dict)
        except KeyError:
            print('Yaml File not specified. Using only input flags and config file.')
            return config_dict
        print('Using input flags, config file, and yaml file.')
        config_yaml_flags_dict = self._merge_a_into_b_simple(flags, config_yaml_dict)
        return config_yaml_flags_dict

    def check_dict_keys(self, config_yaml_flags_dict):
        """ Fill in all optional keys with None. Exit in a crucial key is not defined. """
        crucial_keys = ['MODEL_DIRECTORY', 'SAVE_DIRECTORY']
        for key in crucial_keys:
            if key not in config_yaml_flags_dict:
                print('You must define %s. Now exiting...' % key)
                exit()
        optional_keys = ['RESTORE_SLIM_FILE', 'RESTORE_META', 'RESTORE_SLIM', 'SEED', 'GPU']
        for key in optional_keys:
            if key not in config_yaml_flags_dict:
                config_yaml_flags_dict[key] = None
                print('%s in flags, yaml or config dictionary was not found.' % key)
        if 'RUN_NUM' not in config_yaml_flags_dict:
            config_yaml_flags_dict['RUN_NUM'] = 0
        if 'NUM_EPOCHS' not in config_yaml_flags_dict:
            config_yaml_flags_dict['NUM_EPOCHS'] = 1
        return config_yaml_flags_dict

    def _check_file_io(self):
        """ Create and define logging directory """
        folder = 'Model' + str(self.flags['RUN_NUM']) + '/'
        folder_restore = 'Model' + str(self.flags['MODEL_RESTORE']) + '/'
        self.flags['RESTORE_DIRECTORY'] = self.flags['SAVE_DIRECTORY'] + self.flags[
            'MODEL_DIRECTORY'] + folder_restore
        self.flags['LOGGING_DIRECTORY'] = self.flags['SAVE_DIRECTORY'] + self.flags[
            'MODEL_DIRECTORY'] + folder
        self.make_directory(self.flags['LOGGING_DIRECTORY'])
        sys.stdout = Logger(self.flags['LOGGING_DIRECTORY'] + 'ModelInformation.log')
        print(self.flags)

    def _set_tf_functions(self):
        """ Sets up summary writer, saver, and session, with configurable gpu visibility """
        merged = tf.summary.merge_all()
        saver = tf.train.Saver()
        if type(self.flags['GPU']) is int:
            os.environ["CUDA_VISIBLE_DEVICES"] = str(self.flags['GPU'])
            print('Using GPU %d' % self.flags['GPU'])
        gpu_options = tf.GPUOptions(allow_growth=True)
        config = tf.ConfigProto(log_device_placement=False, gpu_options=gpu_options)
        sess = tf.Session(config=config)
        writer = tf.summary.FileWriter(self.flags['LOGGING_DIRECTORY'], sess.graph)
        return merged, saver, sess, writer

    def _get_restore_meta_file(self):
        return 'part_' + str(self.flags['FILE_EPOCH']) + '.ckpt.meta'

    def _restore_meta(self):
        """ Restore from meta file. 'RESTORE_META_FILE' is expected to have .meta at the end. """
        restore_meta_file = self._get_restore_meta_file()
        filename = self.flags['RESTORE_DIRECTORY'] + self._get_restore_meta_file()
        new_saver = tf.train.import_meta_graph(filename)
        new_saver.restore(self.sess, filename[:-5])
        print("Model restored from %s" % restore_meta_file)

    def _restore_slim(self, variables):
        """ Restore from tf-slim file (usually a ImageNet pre-trained model). """
        variables_to_restore = self.get_variables_in_checkpoint_file(self.flags['RESTORE_SLIM_FILE'])
        variables_to_restore = {self.name_in_checkpoint(v): v for v in variables if (self.name_in_checkpoint(v) in variables_to_restore)}
        if variables_to_restore is []:
            print('Check the SLIM checkpoint filename. No model variables matched the checkpoint variables.')
            exit()
        saver = tf.train.Saver(variables_to_restore)
        saver.restore(self.sess, self.flags['RESTORE_SLIM_FILE'])
        print("Model restored from %s" % self.flags['RESTORE_SLIM_FILE'])

    def _initialize_model(self):
        """ Initialize the defined network and restore from files is so specified. """
        # Initialize all variables first
        self.sess.run(tf.local_variables_initializer())
        self.sess.run(tf.global_variables_initializer())
        if self.flags['RESTORE_META'] == 1:
            print('Restoring from .meta file')
            self._restore_meta()
        elif self.flags['RESTORE_SLIM'] == 1:
            print('Restoring TF-Slim Model.')
            all_model_variables = tf.global_variables()
            self._restore_slim(all_model_variables)
        else:
            print("Model training from scratch.")

    def _init_uninit_vars(self):
        """ Initialize all other trainable variables, i.e. those which are uninitialized """
        uninit_vars = self.sess.run(tf.report_uninitialized_variables())
        vars_list = list()
        for v in uninit_vars:
            var = v.decode("utf-8")
            vars_list.append(var)
        uninit_vars_tf = [v for v in tf.global_variables() if v.name.split(':')[0] in vars_list]
        self.sess.run(tf.variables_initializer(var_list=uninit_vars_tf))

    def _save_model(self, section):
        """ Save model in the logging directory """
        checkpoint_name = self.flags['LOGGING_DIRECTORY'] + 'part_%d' % section + '.ckpt'
        save_path = self.saver.save(self.sess, checkpoint_name)
        print("Model saved in file: %s" % save_path)

    def _record_training_step(self, summary):
        """ Adds summary to writer and increments the step. """
        self.writer.add_summary(summary=summary, global_step=self.step)
        self.step += 1

    def _set_seed(self):
        """ Set random seed for numpy and tensorflow packages """
        if self.flags['SEED'] is not None:
            tf.set_random_seed(self.flags['SEED'])
            np.random.seed(self.flags['SEED'])

    def _summaries(self):
        """ Print out summaries for every variable. Can be overriden in main function. """
        for var in tf.trainable_variables():
            tf.summary.histogram(var.name, var)
            print(var.name)

    def _data(self):
        """Define data"""
        raise NotImplementedError

    def _network(self):
        """Define network"""
        raise NotImplementedError

    def _optimizer(self):
        """Define optimizer"""
        raise NotImplementedError

    def get_flags(self):
        return self.flags

    @staticmethod
    def make_directory(folder_path):
        """ Make directory at folder_path if it does not exist """
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

    @staticmethod
    def print_log(message):
        """ Print message to terminal and to logging document if applicable """
        print(message)
        logging.info(message)

    @staticmethod
    def check_str(obj):
        """ Returns a string for various input types """
        if isinstance(obj, str):
            return obj
        if isinstance(obj, float):
            return str(int(obj))
        else:
            return str(obj)

    @staticmethod
    def name_in_checkpoint(var):
        """ Removes 'model' scoping if it is present in order to properly restore weights. """
        if var.op.name.startswith('model/'):
            return var.op.name[len('model/'):]

    @staticmethod
    def get_variables_in_checkpoint_file(filename):
        try:
            reader = pywrap_tensorflow.NewCheckpointReader(filename)
            var_to_shape_map = reader.get_variable_to_shape_map()
            return var_to_shape_map
        except Exception as e:  # pylint: disable=broad-except
            print(str(e))
            if "corrupted compressed block contents" in str(e):
                print("It's likely that your checkpoint file has been compressed "
                      "with SNAPPY.")

    def _merge_a_into_b(self, a, b):
        """Merge config dictionary a into config dictionary b, clobbering the
        options in b whenever they are also specified in a.
        """
        from easydict import EasyDict as edict
        if type(a) is not edict:
            return

        for k, v in a.items():
            # a must specify keys that are in b
            if k not in b:
                raise KeyError('{} is not a valid config key'.format(k))

            # the types must match, too
            old_type = type(b[k])
            if old_type is not type(v):
                if isinstance(b[k], np.ndarray):
                    v = np.array(v, dtype=b[k].dtype)
                else:
                    raise ValueError(('Type mismatch ({} vs. {}) '
                                      'for config key: {}').format(type(b[k]),
                                                                   type(v), k))

            # recursively merge dicts
            if type(v) is edict:
                try:
                    self._merge_a_into_b(a[k], b[k])
                except:
                    print('Error under config key: {}'.format(k))
                    raise
            else:
                b[k] = v
        return b

    def _merge_a_into_b_simple(self, a, b):
        """Merge config dictionary a into config dictionary b, clobbering the
        options in b whenever they are also specified in a. Do not do any checking.
        """
        for k, v in a.items():
            b[k] = v
        return b

    def cfg_from_file(self, yaml_filename, config_dict):
        """Load a config file and merge it into the default options."""
        import yaml
        from easydict import EasyDict as edict
        with open(yaml_filename, 'r') as f:
            yaml_cfg = edict(yaml.load(f))

        return self._merge_a_into_b(yaml_cfg, config_dict)


class Logger(object):
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "a")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        #this flush method is needed for python 3 compatibility.
        #this handles the flush command by doing nothing.
        #you might want to specify some extra behavior here.
        pass


class Layers:
    """
    A Class to facilitate network creation in TensorFlow.
    Methods: conv2d, deconv2d, cflatten, maxpool, avgpool, res_layer, noisy_and, batch_norm
    """

    def __init__(self, x):
        """
        Initialize model Layers.
        .input = numpy array
        .count = dictionary to keep count of number of certain types of layers for naming purposes
        """
        self.input = x  # initialize input tensor
        self.count = {'conv': 0, 'deconv': 0, 'fc': 0, 'flat': 0, 'mp': 0, 'up': 0, 'ap': 0, 'rn': 0}

    def conv2d(self, filter_size, output_channels, stride=1, padding='SAME', bn=True, activation_fn=tf.nn.relu,
               b_value=0.0, s_value=1.0, trainable=True):
        """
        2D Convolutional Layer.
        :param filter_size: int. assumes square filter
        :param output_channels: int
        :param stride: int
        :param padding: 'VALID' or 'SAME'
        :param activation_fn: tf.nn function
        :param b_value: float
        :param s_value: float
        """
        self.count['conv'] += 1
        scope = 'conv_' + str(self.count['conv'])
        with tf.variable_scope(scope):

            # Conv function
            input_channels = self.input.get_shape()[3]
            if filter_size == 0:  # outputs a 1x1 feature map; used for FCN
                filter_size = self.input.get_shape()[2]
                padding = 'VALID'
            output_shape = [filter_size, filter_size, input_channels, output_channels]
            w = self.weight_variable(name='weights', shape=output_shape, trainable=trainable)
            self.input = tf.nn.conv2d(self.input, w, strides=[1, stride, stride, 1], padding=padding)

            if bn is True:  # batch normalization
                self.input = self.batch_norm(self.input)
            if b_value is not None:  # bias value
                b = self.const_variable(name='bias', shape=[output_channels], value=b_value, trainable=trainable)
                self.input = tf.add(self.input, b)
            if s_value is not None:  # scale value
                s = self.const_variable(name='scale', shape=[output_channels], value=s_value, trainable=trainable)
                self.input = tf.multiply(self.input, s)
            if activation_fn is not None:  # activation function
                self.input = activation_fn(self.input)
        print(scope + ' output: ' + str(self.input.get_shape()))

    def convnet(self, filter_size, output_channels, stride=None, padding=None, activation_fn=None, b_value=None,
                s_value=None, bn=None, trainable=True):
        '''
        Shortcut for creating a 2D Convolutional Neural Network in one line
        Stacks multiple conv2d layers, with arguments for each layer defined in a list.
        If an argument is left as None, then the conv2d defaults are kept
        :param filter_sizes: int. assumes square filter
        :param output_channels: int
        :param stride: int
        :param padding: 'VALID' or 'SAME'
        :param activation_fn: tf.nn function
        :param b_value: float
        :param s_value: float
        '''
        # Number of layers to stack
        depth = len(filter_size)

        # Default arguments where None was passed in
        if stride is None:
            stride = np.ones(depth)
        if padding is None:
            padding = ['SAME'] * depth
        if activation_fn is None:
            activation_fn = [tf.nn.relu] * depth
        if b_value is None:
            b_value = np.zeros(depth)
        if s_value is None:
            s_value = np.ones(depth)
        if bn is None:
            bn = [True] * depth

            # Make sure that number of layers is consistent
        assert len(output_channels) == depth
        assert len(stride) == depth
        assert len(padding) == depth
        assert len(activation_fn) == depth
        assert len(b_value) == depth
        assert len(s_value) == depth
        assert len(bn) == depth

        # Stack convolutional layers
        for l in range(depth):
            self.conv2d(filter_size=filter_size[l],
                        output_channels=output_channels[l],
                        stride=stride[l],
                        padding=padding[l],
                        activation_fn=activation_fn[l],
                        b_value=b_value[l],
                        s_value=s_value[l],
                        bn=bn[l], trainable=trainable)

    def deconv2d(self, filter_size, output_channels, stride=1, padding='SAME', activation_fn=tf.nn.relu, b_value=0.0,
                 s_value=1.0, bn=True, trainable=True):
        """
        2D Deconvolutional Layer
        :param filter_size: int. assumes square filter
        :param output_channels: int
        :param stride: int
        :param padding: 'VALID' or 'SAME'
        :param activation_fn: tf.nn function
        :param b_value: float
        :param s_value: float
        """
        self.count['deconv'] += 1
        scope = 'deconv_' + str(self.count['deconv'])
        with tf.variable_scope(scope):

            # Calculate the dimensions for deconv function
            batch_size = tf.shape(self.input)[0]
            input_height = tf.shape(self.input)[1]
            input_width = tf.shape(self.input)[2]

            if padding == "VALID":
                out_rows = (input_height - 1) * stride + filter_size
                out_cols = (input_width - 1) * stride + filter_size
            else:  # padding == "SAME":
                out_rows = input_height * stride
                out_cols = input_width * stride

            # Deconv function
            input_channels = self.input.get_shape()[3]
            output_shape = [filter_size, filter_size, output_channels, input_channels]
            w = self.weight_variable(name='weights', shape=output_shape, trainable=trainable)
            deconv_out_shape = tf.stack([batch_size, out_rows, out_cols, output_channels])
            self.input = tf.nn.conv2d_transpose(self.input, w, deconv_out_shape, [1, stride, stride, 1], padding)

            if bn is True:  # batch normalization
                self.input = self.batch_norm(self.input)
            if b_value is not None:  # bias value
                b = self.const_variable(name='bias', shape=[output_channels], value=b_value, trainable=trainable)
                self.input = tf.add(self.input, b)
            if s_value is not None:  # scale value
                s = self.const_variable(name='scale', shape=[output_channels], value=s_value, trainable=trainable)
                self.input = tf.multiply(self.input, s)
            if activation_fn is not None:  # non-linear activation function
                self.input = activation_fn(self.input)
        print(scope + ' output: ' + str(self.input.get_shape()))  # print shape of output

    def deconvnet(self, filter_sizes, output_channels, strides=None, padding=None, activation_fn=None, b_value=None,
                  s_value=None, bn=None, trainable=True):
        '''
        Shortcut for creating a 2D Deconvolutional Neural Network in one line
        Stacks multiple deconv2d layers, with arguments for each layer defined in a list.
        If an argument is left as None, then the conv2d defaults are kept
        :param filter_sizes: int. assumes square filter
        :param output_channels: int
        :param stride: int
        :param padding: 'VALID' or 'SAME'
        :param activation_fn: tf.nn function
        :param b_value: float
        :param s_value: float
        '''
        # Number of layers to stack
        depth = len(filter_sizes)

        # Default arguments where None was passed in
        if strides is None:
            strides = np.ones(depth)
        if padding is None:
            padding = ['SAME'] * depth
        if activation_fn is None:
            activation_fn = [tf.nn.relu] * depth
        if b_value is None:
            b_value = np.zeros(depth)
        if s_value is None:
            s_value = np.ones(depth)
        if bn is None:
            bn = [True] * depth

            # Make sure that number of layers is consistent
        assert len(output_channels) == depth
        assert len(strides) == depth
        assert len(padding) == depth
        assert len(activation_fn) == depth
        assert len(b_value) == depth
        assert len(s_value) == depth
        assert len(bn) == depth

        # Stack convolutional layers
        for l in range(depth):
            self.deconv2d(filter_size=filter_sizes[l], output_channels=output_channels[l], stride=strides[l],
                          padding=padding[l], activation_fn=activation_fn[l], b_value=b_value[l], s_value=s_value[l],
                          bn=bn[l], trainable=trainable)

    def flatten(self, keep_prob=1):
        """
        Flattens 4D Tensor (from Conv Layer) into 2D Tensor (to FC Layer)
        :param keep_prob: int. set to 1 for no dropout
        """
        self.count['flat'] += 1
        scope = 'flat_' + str(self.count['flat'])
        with tf.variable_scope(scope):
            # Reshape function
            input_nodes = tf.Dimension(
                self.input.get_shape()[1] * self.input.get_shape()[2] * self.input.get_shape()[3])
            output_shape = tf.stack([-1, input_nodes])
            self.input = tf.reshape(self.input, output_shape)

            # Dropout function
            if keep_prob != 1:
                self.input = tf.nn.dropout(self.input, keep_prob=keep_prob)
        print(scope + ' output: ' + str(self.input.get_shape()))

    def fc(self, output_nodes, keep_prob=1, activation_fn=tf.nn.relu, b_value=0.0, s_value=1.0, bn=True,
           trainable=True):
        """
        Fully Connected Layer
        :param output_nodes: int
        :param keep_prob: int. set to 1 for no dropout
        :param activation_fn: tf.nn function
        :param b_value: float or None
        :param s_value: float or None
        :param bn: bool
        """
        self.count['fc'] += 1
        scope = 'fc_' + str(self.count['fc'])
        with tf.variable_scope(scope):

            # Flatten if necessary
            if len(self.input.get_shape()) == 4:
                input_nodes = tf.Dimension(
                    self.input.get_shape()[1] * self.input.get_shape()[2] * self.input.get_shape()[3])
                output_shape = tf.stack([-1, input_nodes])
                self.input = tf.reshape(self.input, output_shape)

            # Matrix Multiplication Function
            input_nodes = self.input.get_shape()[1]
            output_shape = [input_nodes, output_nodes]
            w = self.weight_variable(name='weights', shape=output_shape, trainable=trainable)
            self.input = tf.matmul(self.input, w)

            if bn is True:  # batch normalization
                self.input = self.batch_norm(self.input, 'fc')
            if b_value is not None:  # bias value
                b = self.const_variable(name='bias', shape=[output_nodes], value=b_value, trainable=trainable)
                self.input = tf.add(self.input, b)
            if s_value is not None:  # scale value
                s = self.const_variable(name='scale', shape=[output_nodes], value=s_value, trainable=trainable)
                self.input = tf.multiply(self.input, s)
            if activation_fn is not None:  # activation function
                self.input = activation_fn(self.input)
            if keep_prob != 1:  # dropout function
                self.input = tf.nn.dropout(self.input, keep_prob=keep_prob)
        print(scope + ' output: ' + str(self.input.get_shape()))

    def maxpool(self, k=2, s=None, globe=False):
        """
        Takes max value over a k x k area in each input map, or over the entire map (global = True)
        :param k: int
        :param globe:  int, whether to pool over each feature map in its entirety
        """
        self.count['mp'] += 1
        scope = 'maxpool_' + str(self.count['mp'])
        with tf.variable_scope(scope):
            if globe is True:  # Global Pool Parameters
                k1 = self.input.get_shape()[1]
                k2 = self.input.get_shape()[2]
                s1 = 1
                s2 = 1
                padding = 'VALID'
            else:
                k1 = k
                k2 = k
                if s is None:
                    s1 = k
                    s2 = k
                else:
                    s1 = s
                    s2 = s
                padding = 'SAME'
            # Max Pool Function
            self.input = tf.nn.max_pool(self.input, ksize=[1, k1, k2, 1], strides=[1, s1, s2, 1], padding=padding)
        print(scope + ' output: ' + str(self.input.get_shape()))

    def avgpool(self, k=2, s=None, globe=False):
        """
        Averages the values over a k x k area in each input map, or over the entire map (global = True)
        :param k: int
        :param globe: int, whether to pool over each feature map in its entirety
        """
        self.count['ap'] += 1
        scope = 'avgpool_' + str(self.count['mp'])
        with tf.variable_scope(scope):
            if globe is True:  # Global Pool Parameters
                k1 = self.input.get_shape()[1]
                k2 = self.input.get_shape()[2]
                s1 = 1
                s2 = 1
                padding = 'VALID'
            else:
                k1 = k
                k2 = k
                if s is None:
                    s1 = k
                    s2 = k
                else:
                    s1 = s
                    s2 = s
                padding = 'SAME'
            # Average Pool Function
            self.input = tf.nn.avg_pool(self.input, ksize=[1, k1, k2, 1], strides=[1, s1, s2, 1], padding=padding)
        print(scope + ' output: ' + str(self.input.get_shape()))

    def res_layer(self, output_channels, filter_size=3, stride=1, activation_fn=tf.nn.relu, bottle=False,
                  trainable=True):
        """
        Residual Layer: Input -> BN, Act_fn, Conv1, BN, Act_fn, Conv 2 -> Output.  Return: Input + Output
        If stride > 1 or number of filters changes, decrease dims of Input by passing through a 1 x 1 Conv Layer
        The bottle option changes the Residual layer blocks to the bottleneck structure
        :param output_channels: int
        :param filter_size: int. assumes square filter
        :param stride: int
        :param activation_fn: tf.nn function
        :param bottle: boolean
        """
        self.count['rn'] += 1
        scope = 'resnet_' + str(self.count['rn'])
        input_channels = self.input.get_shape()[3]
        with tf.variable_scope(scope):

            # Determine Additive Output if dimensions change
            # Decrease Input dimension with 1 x 1 Conv Layer with stride > 1
            if (stride != 1) or (input_channels != output_channels):
                with tf.variable_scope('conv0'):
                    output_shape = [1, 1, input_channels, output_channels]
                    w = self.weight_variable(name='weights', shape=output_shape, trainable=trainable)
                    additive_output = tf.nn.conv2d(self.input, w, strides=[1, stride, stride, 1], padding='SAME')
                    b = self.const_variable(name='bias', shape=[output_channels], value=0.0)
                    additive_output = tf.add(additive_output, b)
            else:
                additive_output = self.input

            # First Conv Layer. Implement stride in this layer if desired.
            with tf.variable_scope('conv1'):
                fs = 1 if bottle else filter_size
                oc = output_channels // 4 if bottle else output_channels
                output_shape = [fs, fs, input_channels, oc]
                w = self.weight_variable(name='weights', shape=output_shape, trainable=trainable)
                self.input = self.batch_norm(self.input)
                self.input = activation_fn(self.input)
                self.input = tf.nn.conv2d(self.input, w, strides=[1, stride, stride, 1], padding='SAME')
                b = self.const_variable(name='bias', shape=[oc], value=0.0)
                self.input = tf.add(self.input, b)
            # Second Conv Layer
            with tf.variable_scope('conv2'):
                input_channels = self.input.get_shape()[3]
                oc = output_channels // 4 if bottle else output_channels
                output_shape = [filter_size, filter_size, input_channels, oc]
                w = self.weight_variable(name='weights', shape=output_shape, trainable=trainable)
                self.input = self.batch_norm(self.input)
                self.input = activation_fn(self.input)
                self.input = tf.nn.conv2d(self.input, w, strides=[1, 1, 1, 1], padding='SAME')
                b = self.const_variable(name='bias', shape=[oc], value=0.0)
                self.input = tf.add(self.input, b)
            if bottle:
                # Third Conv Layer
                with tf.variable_scope('conv3'):
                    input_channels = self.input.get_shape()[3]
                    output_shape = [1, 1, input_channels, output_channels]
                    w = self.weight_variable(name='weights', shape=output_shape, trainable=trainable)
                    self.input = self.batch_norm(self.input)
                    self.input = activation_fn(self.input)
                    self.input = tf.nn.conv2d(self.input, w, strides=[1, 1, 1, 1], padding='SAME')
                    b = self.const_variable(name='bias', shape=[output_channels], value=0.0)
                    self.input = tf.add(self.input, b)

            # Add input and output for final return
            self.input = self.input + additive_output
        print(scope + ' output: ' + str(self.input.get_shape()))

    def noisy_and(self, num_classes, trainable=True):
        """ Multiple Instance Learning (MIL), flexible pooling function
        :param num_classes: int, determine number of output maps
        """
        assert self.input.get_shape()[3] == num_classes  # input tensor should have map depth equal to # of classes
        scope = 'noisyAND'
        with tf.variable_scope(scope):
            a = self.const_variable(name='a', shape=[1], value=1.0, trainable=trainable)
            b = self.const_variable(name='b', shape=[1, num_classes], value=0.0, trainable=trainable)
            mean = tf.reduce_mean(self.input, axis=[1, 2])
            self.input = (tf.nn.sigmoid(a * (mean - b)) - tf.nn.sigmoid(-a * b)) / (
                tf.sigmoid(a * (1 - b)) - tf.sigmoid(-a * b))
        print(scope + ' output: ' + str(self.input.get_shape()))

    def get_output(self):
        """
        :return tf.Tensor, output of network
        """
        return self.input

    def batch_norm(self, x, type='conv', epsilon=1e-3):
        """
        Batch Normalization: Apply mean subtraction and variance scaling
        :param x: input feature map stack
        :param type: string, either 'conv' or 'fc'
        :param epsilon: float
        :return: output feature map stack
        """
        # Determine indices over which to calculate moments, based on layer type
        if type == 'conv':
            size = [0, 1, 2]
        else:  # type == 'fc'
            size = [0]

        # Calculate batch mean and variance
        batch_mean1, batch_var1 = tf.nn.moments(x, size, keep_dims=True)

        # Apply the initial batch normalizing transform
        z1_hat = (x - batch_mean1) / tf.sqrt(batch_var1 + epsilon)
        return z1_hat

    @staticmethod
    def print_log(message):
        """ Writes a message to terminal screen and logging file, if applicable"""
        print(message)
        logging.info(message)

    @staticmethod
    def weight_variable(name, shape, trainable):
        """
        :param name: string
        :param shape: 4D array
        :return: tf variable
        """
        w = tf.get_variable(name=name, shape=shape, initializer=tf.contrib.layers.variance_scaling_initializer(),
                            trainable=trainable)
        weights_norm = tf.reduce_sum(tf.nn.l2_loss(w),
                                     name=name + '_norm')  # Should user want to optimize weight decay
        tf.add_to_collection('weight_losses', weights_norm)
        return w

    @staticmethod
    def const_variable(name, shape, value, trainable):
        """
        :param name: string
        :param shape: 1D array
        :param value: float
        :return: tf variable
        """
        return tf.get_variable(name, shape, initializer=tf.constant_initializer(value), trainable=trainable)
