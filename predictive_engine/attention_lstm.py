# predictive_engine/attention_lstm.py

import tensorflow as tf
from tensorflow.keras.layers import Layer, Dense, Permute, Multiply, Lambda, Activation, Flatten, RepeatVector
from tensorflow.keras import backend as K

class AttentionLayer(Layer):
    """
    Capa de atención personalizada para LSTM
    Permite al modelo enfocarse en pasos de tiempo específicos
    """
    def __init__(self, **kwargs):
        super(AttentionLayer, self).__init__(**kwargs)
        
    def build(self, input_shape):
        # Crea los pesos para la capa de atención
        self.W = self.add_weight(
            name="attention_weight",
            shape=(input_shape[-1], 1),
            initializer="random_normal",
            trainable=True
        )
        self.b = self.add_weight(
            name="attention_bias",
            shape=(input_shape[1], 1),
            initializer="zeros",
            trainable=True
        )
        super(AttentionLayer, self).build(input_shape)
    
    def call(self, inputs):
        # Calcular puntuaciones de atención
        e = K.tanh(K.dot(inputs, self.W) + self.b)
        # Obtener pesos de atención vía softmax
        a = K.softmax(e, axis=1)
        # Aplicar atención a las entradas
        output = K.sum(inputs * a, axis=1)
        return output
    
    def compute_output_shape(self, input_shape):
        return (input_shape[0], input_shape[-1])
    
    def get_config(self):
        return super(AttentionLayer, self).get_config()

def create_attention_lstm_model(input_shape, output_shape=1, lstm_units=128, dropout_rate=0.2):
    """
    Crea un modelo LSTM con mecanismo de atención
    
    Args:
        input_shape: Forma de los datos de entrada (sequence_length, features)
        output_shape: Número de salidas (1 para clasificación binaria)
        lstm_units: Número de unidades en la capa LSTM
        dropout_rate: Tasa de dropout para regularización
    
    Returns:
        Modelo compilado
    """
    # Importar las clases necesarias
    from tensorflow.keras.models import Model
    from tensorflow.keras.layers import Input, LSTM, Dense, Dropout
    from tensorflow.keras.optimizers import Adam
    
    # Capa de entrada
    inputs = Input(shape=input_shape)
    
    # Primera capa LSTM (devuelve secuencias)
    lstm_out = LSTM(lstm_units, return_sequences=True)(inputs)
    lstm_out = Dropout(dropout_rate)(lstm_out)
    
    # Segunda capa LSTM (devuelve secuencias)
    lstm_out = LSTM(lstm_units//2, return_sequences=True)(lstm_out)
    lstm_out = Dropout(dropout_rate)(lstm_out)
    
    # Capa de atención
    attention_out = AttentionLayer()(lstm_out)
    
    # Capas densas para clasificación
    dense_out = Dense(lstm_units//4, activation='relu')(attention_out)
    dense_out = Dropout(dropout_rate)(dense_out)
    outputs = Dense(output_shape, activation='sigmoid')(dense_out)
    
    # Crear y compilar modelo
    model = Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer=Adam(learning_rate=0.001),
        loss='binary_crossentropy',
        metrics=['accuracy']
    )
    
    return model

# Función alternativa usando capas básicas de Keras
def create_attention_lstm_model_simplified(input_shape, output_shape=1, lstm_units=128, dropout_rate=0.2):
    """
    Implementación alternativa usando capas estándar de Keras
    """
    from tensorflow.keras.models import Model
    from tensorflow.keras.layers import Input, LSTM, Dense, Dropout, TimeDistributed
    
    # Capa de entrada
    inputs = Input(shape=input_shape)
    
    # Primera capa LSTM
    lstm_out = LSTM(lstm_units, return_sequences=True)(inputs)
    lstm_out = Dropout(dropout_rate)(lstm_out)
    
    # Segunda capa LSTM
    lstm_out = LSTM(lstm_units//2, return_sequences=True)(lstm_out)
    lstm_out = Dropout(dropout_rate)(lstm_out)
    
    # Mecanismo de atención
    attention = TimeDistributed(Dense(1, activation='tanh'))(lstm_out)
    attention = Flatten()(attention)
    attention = Activation('softmax')(attention)
    attention = RepeatVector(lstm_units//2)(attention)
    attention = Permute([2, 1])(attention)
    
    # Aplicar atención
    merged = Multiply()([lstm_out, attention])
    merged = Lambda(lambda x: K.sum(x, axis=1))(merged)
    
    # Capas densas finales
    dense_out = Dense(lstm_units//4, activation='relu')(merged)
    dense_out = Dropout(dropout_rate)(dense_out)
    outputs = Dense(output_shape, activation='sigmoid')(dense_out)
    
    # Crear y compilar modelo
    model = Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer='adam',
        loss='binary_crossentropy',
        metrics=['accuracy']
    )
    
    return model