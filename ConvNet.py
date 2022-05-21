from os import access
import numpy as np
import math

class Layer:
    def __init__(self):
        self.optimization_params = None

    def forward(self):
        raise NotImplementedError()

    def backward(self):
        raise NotImplementedError()

class ConvNet:
    def __init__(self):
        self.layers    = []
        self.hist_acc  = []
        self.hist_loss = []

    def add(self, layer):
        self.layers.append(layer)

    def evaluate(self, X_test, Y_test):
        total_size  = X_test.shape[0]
        num_batches = total_size // 100
        X_batches   = np.split(X_test, num_batches, axis = 0)
        Y_batches   = np.split(Y_test, num_batches, axis = 1)

        avg_acc  = 0.0
        avg_loss = 0.0
        num_acc  = 0
        
        for batch_idx, (batch_X, batch_Y) in enumerate(zip(X_batches, Y_batches)):
            forward_output = batch_X

            # Forward pass
            for layer in self.layers:
                forward_output = layer.forward(forward_output)

            # Assumes log-loss is used w/ softmax activation
            loss = -(batch_Y * np.log(forward_output))
            loss = np.sum(loss, axis = 0)
            cost = np.average(loss)

            accurate = np.argmax(forward_output, axis = 0) == np.argmax(batch_Y, axis = 0)
            num_acc += np.sum(accurate)
            accuracy = np.average(accurate)

            avg_acc  += accuracy  / num_batches
            avg_loss += cost      / num_batches

            progress_batch = batch_idx / num_batches
            progress_bar   = ('=' * (math.ceil(progress_batch * 30) - 1)) + '>'
            progress_bar   = progress_bar + (' ' * (30 - len(progress_bar)))
            output_string  = '[Epoch 1/1] - [{}] - loss: {:.4f} - train_accuracy: {:.4f}'.format(
                progress_bar, cost, accuracy 
            )
            print(output_string, end = '\r')

        print()
        return avg_loss, num_acc / total_size

    def fit(self, X, Y, num_epochs, learning_rate):
        self.hist_acc  = []
        self.hist_loss = []

        for layer in self.layers:
            layer.optimization_params = {
                'learning_rate': learning_rate,
                'momentum'     : 0.9,
            }

        num_batches = X.shape[0] // 64
        X_batches   = np.split(X, num_batches, axis = 0)
        Y_batches   = np.split(Y, num_batches, axis = 1)

        for epoch in range(num_epochs):
            avg_acc  = 0.0
            avg_loss = 0.0

            for batch_idx, (batch_X, batch_Y) in enumerate(zip(X_batches, Y_batches)):
                forward_output = batch_X

                # Forward pass
                for layer in self.layers:
                    forward_output = layer.forward(forward_output)

                # Assumes log-loss is used w/ softmax activation
                loss = -(batch_Y * np.log(forward_output))
                loss = np.sum(loss, axis = 0)
                cost = np.average(loss)

                acc  = np.average(np.argmax(forward_output, axis = 0) == np.argmax(batch_Y, axis = 0))

                avg_acc  += acc  / num_batches
                avg_loss += cost / num_batches

                # Backward pass
                backward_output = -(batch_Y / forward_output) + 1e-8 

                for layer in reversed(self.layers):
                    backward_output = layer.backward(backward_output)

                progress_batch = batch_idx / num_batches
                progress_bar   = ('=' * (math.ceil(progress_batch * 30) - 1)) + '>'
                progress_bar   = progress_bar + (' ' * (30 - len(progress_bar)))
                output_string  = '[Epoch {:2}/{:2}] - [{}] - loss: {:.4f} - train_accuracy: {:.4f}'.format(
                    epoch + 1, num_epochs, progress_bar, 
                    cost if batch_idx < num_batches - 1 else avg_loss, 
                    acc  if batch_idx < num_batches - 1 else avg_acc
                )
                print(output_string, end = '\r')

            print()
            self.hist_loss.append(avg_loss)
            self.hist_acc.append(avg_acc)
        return self.hist_loss, self.hist_acc

class PoolLayer(Layer):
    def __init__(self, filter_size = 2, stride = 2, mode = 'avg'):
        self.mode = mode
        assert self.mode in ['avg']

        self.filter_size = filter_size
        self.stride = stride

    def forward(self, input_batch):
        self.input_batch = input_batch

        self.orig_shape   = input_batch.shape
        self.batch_size   = input_batch.shape[0]
        self.img_channels = input_batch.shape[1]

        self.out_h  = (self.input_batch.shape[2] - self.filter_size) // self.stride + 1
        self.out_w  = (self.input_batch.shape[3] - self.filter_size) // self.stride + 1

        img_strides = self.input_batch.strides

        self.conv_strides = (
            img_strides[0],                                  # next image
            0 if self.img_channels == 1 else img_strides[1], # next channel
            img_strides[2] * self.stride,                    # next window (y)
            img_strides[3] * self.stride,                    # next window (x)
            img_strides[2],                                  # next cell (y)
            img_strides[3]                                   # next cell (x)
        )

        self.window_shape = (
            self.batch_size, self.img_channels, self.out_h, self.out_w,
            self.filter_size, self.filter_size,
        )

        self.conv_windows = np.lib.stride_tricks.as_strided(
            self.input_batch,
            shape   = self.window_shape,
            strides = self.conv_strides,
        )
        
        self.pooled = np.average(self.conv_windows, axis = (4, 5))
        return self.pooled
    
    def backward(self, dL_da):
        self.dZ_next  = np.full(self.input_batch.shape, 1.0 / (self.filter_size ** 2))
        self.dZ_next *= np.tile(dL_da, (1, 1, self.stride, self.stride))

        assert self.dZ_next.shape == self.input_batch.shape, "[Internal Error] Incorrect gradient calculation {}, {}".format(self.dZ_next.shape, self.pooled.shape)
        return self.dZ_next

class FlattenLayer(Layer):
    def __init__(self):
        pass

    def forward(self, input_batch):
        self.orig_shape = input_batch.shape
        self.batch_size = self.orig_shape[0]
        
        return input_batch.reshape(self.batch_size, -1).T

    def backward(self, dLdA):
        return dLdA.reshape(self.orig_shape)

class DenseLayer(Layer):
    def __init__(self, num_units, activation = 'softmax'):
        assert activation in ['softmax', 'relu', 'sigmoid', 'tanh'], 'Please select a supported activation function'

        self.num_units  = num_units
        self.activation_func = activation
        self.activation = {
            'softmax': lambda z: np.exp(z) / np.sum(np.exp(z), axis = 0),
            'sigmoid': lambda z: 1 / (1 + np.exp(-z)),
            'relu'   : lambda z: np.maximum(0, z),
            'tanh'   : lambda z: np.tanh(z)
        } [activation]

        self.dL_dz_func = {
            'relu'   : lambda dL_da, a: dL_da * (a > 0.0),
            'sigmoid': lambda dL_da, a: dL_da * (a * (1 - a)),
            'tanh'   : lambda dL_da, a: dL_da * (1 - a ** 2),
        }
        

        self.weights = None
        self.biases  = np.zeros((num_units, 1))
        self.vdb     = np.zeros(self.biases.shape)

    # input_batch: (2-D) -> (num_features, batch_size)
    # output     : (2-D) -> (num_units, batch_size)
    def forward(self, input_batch):
        self.input_batch = input_batch
        self.batch_size  = input_batch.shape[1]

        if self.weights is None:
            num_features = input_batch.shape[0]
            self.weights = np.random.randn(self.num_units, num_features) / np.sqrt(2.0 * num_features)
            self.vdw     = np.zeros(self.weights.shape)

        self.z_out  = np.dot(self.weights, input_batch) + self.biases
        if self.activation_func == 'softmax':
            self.z_out -= self.z_out.max(axis = 0) # For numerical stability
        
        self.a_out  = self.activation(self.z_out)

        return self.a_out

    def backward(self, dL_da):
        # since softmax is a vector valued function, i.e the output depends
        # on all the components of the vector, dL_dz is calculated with a special
        # case using the Jacobian
        if self.activation_func == 'softmax':
            self.diags = np.einsum('kx,kw->xwk', self.a_out, np.identity(self.a_out.shape[0]))
            self.da_dz = np.einsum('zx,xk->xkz', -self.a_out, self.a_out.T) + self.diags
            self.dL_dz = np.einsum('xhw,wx->hx', self.da_dz, dL_da)
        else:
            self.dL_dz = self.dL_dz_func[self.activation_func](dL_da, self.a_out)

        # Shapes being the same are not necessarily indicative of erroneous
        # computation, but if they're not even the same then something is definitely wrong
        assert self.dL_dz.shape == self.z_out.shape, "[Internal Error] Incorrect gradient calculation"

        self.dw = np.dot(self.dL_dz, self.input_batch.T) / self.batch_size
        self.db = np.sum(self.dL_dz, axis = 1, keepdims = True) / self.batch_size  

        self.dA_prev = np.dot(self.weights.T, self.dL_dz)  
    
        eta = self.optimization_params['momentum']
        lr  = self.optimization_params['learning_rate']

        self.vdw = (eta * self.vdw) + (1 - eta) * self.dw
        self.vdb = (eta * self.vdb) + (1 - eta) * self.db

        self.weights -= lr * self.vdw
        self.biases  -= lr * self.vdb

        return self.dA_prev

class ConvLayer(Layer):
    def __init__(self, num_filters, filter_size, stride = 1, mode = 'valid'):
        self.num_filters = num_filters
        self.filter_size = filter_size
        self.stride = stride
        self.mode   = mode

        self.biases  = np.zeros((num_filters, 1))
        self.vdb     = np.zeros(self.biases.shape)
        self.filters = None

    # Input batch: (4-D) -> (image_idx, channel, height, width)
    # filters    : (4-D) -> (filter_idx, channel, height, width)
    def forward(self, input_batch):
        self.input_batch = input_batch

        self.orig_shape   = input_batch.shape
        self.batch_size   = input_batch.shape[0]
        self.img_channels = input_batch.shape[1]

        img_h = input_batch.shape[2]
        img_w = input_batch.shape[3]

        if self.filters is None:
            self.filters = np.random.randn(self.num_filters, self.img_channels, 
                                           self.filter_size, self.filter_size)
            self.vdw     = np.zeros(self.filters.shape)
            self.filters = self.filters / np.sqrt(2.0 * (self.filter_size ** 2))
        
        if self.mode == 'same':
            pad_x  = int(np.ceil((self.stride * (img_w - 1) - img_w + self.filter_size) / 2.0))
            pad_y  = int(np.ceil((self.stride * (img_h - 1) - img_h + self.filter_size) / 2.0))

            paddings = ((0, 0), (0, 0), (pad_y, pad_y), (pad_x, pad_x))
            self.input_batch = np.pad(self.input_batch, paddings, mode = 'constant')

        self.out_h  = (self.input_batch.shape[2] - self.filter_size) // self.stride + 1
        self.out_w  = (self.input_batch.shape[3] - self.filter_size) // self.stride + 1

        img_strides = self.input_batch.strides

        self.conv_strides = (
            img_strides[0],                                  # next image
            0 if self.img_channels == 1 else img_strides[1], # next channel
            img_strides[2] * self.stride,                    # next window (y)
            img_strides[3] * self.stride,                    # next window (x)
            img_strides[2],                                  # next cell (y)
            img_strides[3]                                   # next cell (x)
        )

        self.window_shape = (
            self.batch_size, self.img_channels, self.out_h, self.out_w,
            self.filter_size, self.filter_size,
        )

        self.conv_windows = np.lib.stride_tricks.as_strided(
            self.input_batch,
            shape   = self.window_shape,
            strides = self.conv_strides,
        )
        
        self.conv  = np.einsum('xchwij,fcij->xfhw', self.conv_windows, self.filters)
        self.conv  = np.repeat(np.expand_dims(self.biases, axis = (0, 2)), self.conv.shape[0], axis = 0) + self.conv
        self.a_out = np.maximum(0, self.conv) # ReLU

        #print('out shape:', self.a_out.shape)

        return self.a_out
    
    # dLdA  : (4-D) -> (image_idx, num_filter, out_h, out_w)
    # dLdAp : (4-D) -> (image_idx, channel, in_h, in_w)
    def backward(self, dLdA):
        self.dLdZ = dLdA * (self.conv > 0.0)

        self.dW_window_shape = (
            self.batch_size, 
            self.input_batch.shape[1], 
            self.filters.shape[2], 
            self.filters.shape[3],
            self.out_h, self.out_w,
        )

        self.dW_windows = np.lib.stride_tricks.as_strided(
            self.input_batch,
            shape   = self.dW_window_shape,
            strides = self.conv_strides,
        )

        self.dF = np.einsum('xchwjk,xfjk->fchw', self.dW_windows, self.dLdZ) / self.batch_size
        self.db = np.einsum('xfhw->f', self.dLdZ).reshape(-1, 1) / self.batch_size

        # If stride is not 1, pad dZ with zeros -- in between elements -- in the
        # spatial dimensions i.e. the last 2 in dZ.shape
        self.dZ_prev = self.dLdZ

        if self.stride != 1 and self.mode == 'valid':            
            pad_loc_y    = np.repeat(np.arange(self.dZ_prev.shape[2])[1::], 1)
            pad_loc_x    = np.repeat(np.arange(self.dZ_prev.shape[3])[1::], 1)
            #print('before padding dzPrev', self.dZ_prev.shape, self.a_out.shape)
            self.dZ_prev = np.insert(np.insert(self.dZ_prev, pad_loc_y, 0, axis = 2), pad_loc_x, 0, axis = 3)

        # Pad dZ such that a valid convolution with a stride of 1 will result in
        # the same shape as the output of the previous layer
        source_h, source_w = self.orig_shape[2::]

        num_pad_y = int(np.ceil((source_h - self.dZ_prev.shape[2] + self.filter_size - 1) / 2))
        num_pad_x = int(np.ceil((source_w - self.dZ_prev.shape[3] + self.filter_size - 1) / 2))

        #print(num_pad_x, num_pad_y, source_h, source_w, self.dZ_prev.shape)

        paddings = ((0, 0), (0, 0), (num_pad_y, num_pad_y), (num_pad_x, num_pad_x))
        self.padded_dZ_prev = np.pad(self.dZ_prev, paddings, mode = 'constant')
        dZ_prev_strides = self.padded_dZ_prev.strides

        self.dZ_prev_strides = (
            dZ_prev_strides[0],      
            0 if self.num_filters == 1 else dZ_prev_strides[1],
            dZ_prev_strides[2], # stride = 1
            dZ_prev_strides[3], # stride = 1
            dZ_prev_strides[2],      
            dZ_prev_strides[3]       
        )

        self.dZ_prev_windows_shape = (
            self.batch_size, self.num_filters, self.orig_shape[2], self.orig_shape[3],
            self.filter_size, self.filter_size,
        )

        self.dZ_prev_windows = np.lib.stride_tricks.as_strided(
            self.padded_dZ_prev,
            shape   = self.dZ_prev_windows_shape,
            strides = self.dZ_prev_strides
        )

        # Rotate the filters 180 degrees
        self.rotated_filters = np.rot90(np.swapaxes(self.filters, 0, 1), 2, axes = (2, 3))

        # Convolve the padded dZ with the rotated filters
        self.dZ_prev_conv = np.einsum('xfhwij,cfij->xchw', self.dZ_prev_windows, self.rotated_filters)

        eta = self.optimization_params['momentum']
        lr  = self.optimization_params['learning_rate']

        self.vdw = (eta * self.vdw) + (1 - eta) * self.dF
        self.vdb = (eta * self.vdb) + (1 - eta) * self.db

        self.filters -= lr * self.vdw
        self.biases  -= lr * self.vdb

        return self.dZ_prev_conv
