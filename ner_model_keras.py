from tensorflow.keras import Input,Model
from tensorflow.keras.layers import Dropout,Dense,GRU,Bidirectional
import numpy as np
import json,time,collections,random



class NERModel(object):
  def __init__(self,embedding_path, embedding_size,ner_labels):
    self.embedding_path = embedding_path
    self.embedding_size = embedding_size
    self.embedding_dropout_rate = 0.5
    self.hidden_size = 50
    self.ffnn_layer = 2
    self.hidden_dropout_rate = 0.2
    self.embedding_dict = self.load_embeddings()
    self.ner_labels = ner_labels
    self.ner_labels_mappings = {l:i for i,l in enumerate(ner_labels)}

  def load_embeddings(self):
    print("Loading word embeddings from {}...".format(self.embedding_path))
    embeddings = collections.defaultdict(lambda: np.zeros(self.embedding_size))
    for line in open(self.embedding_path):
      splitter = line.find(' ')
      emb = np.fromstring(line[splitter + 1:], np.float32, sep=' ')
      assert len(emb) == self.embedding_size
      embeddings[line[:splitter]] = emb
    print("Finished loading word embeddings")
    return embeddings

  def build(self):
    word_embeddings = Input(shape=(None,self.embedding_size,))
    word_embeddings = Dropout(self.embedding_dropout_rate)(word_embeddings)
    """
    Task 1 Create a two layer Bidirectional GRU and Multi-layer FFNN to compute the ner scores for individual tokens
    The shape of the ner_scores is [batch_size, max_sentence_length, number_of_ner_labels]
    """
    # Bi-directional GRU1 having 50 GRU units i.e. 100 cells with recurrent dropout = 0.2 and return_sequences = True
    word_output = Bidirectional(GRU(50, return_sequences = True, recurrent_dropout = 0.2))(word_embeddings)
    # Bi-directional GRU2 having 50 GRU units i.e. 100 cells with recurrent dropout = 0.2 and return_sequences = True
    word_output = Bidirectional(GRU(50, return_sequences = True, recurrent_dropout = 0.2))(word_output)
    # Dropout layer having rate of 0.2
    dropout_layer_1 = Dropout(self.hidden_dropout_rate)(word_output)
    # Dense layer having 50 neurons and the ReLU Activation Function
    dense_layer_1 = Dense(self.hidden_size, activation='relu')(dropout_layer_1)
    # Dropout layer having rate of 0.2
    dropout_layer_2 = Dropout(self.hidden_dropout_rate)(dense_layer_1)
    # Dense layer having 50 neurons and the ReLU Activation Function
    dense_layer_2 = Dense(self.hidden_size, activation='relu')(dropout_layer_2)
    # Dropout layer having rate of 0.2
    dropout_layer_3 = Dropout(self.hidden_dropout_rate)(dense_layer_2)
    # Output Layer having 5 output neurons and the SoftMax Activation Function
    ner_scores = Dense(5, activation ='softmax')(dropout_layer_3)
    """
    End Task 1 
    """

    self.model = Model(inputs=[word_embeddings],outputs=ner_scores)
    self.model.compile(optimizer='adam',loss="sparse_categorical_crossentropy",metrics=['accuracy'])
    self.model.summary()

  def get_feed_dict_list(self, path,batch_size):
    feed_dict_list = []
    data_sets = json.loads(open(path).readlines()[0])
    sentences = data_sets['sentences']
    ners = data_sets['ners']
    for i in range(0,len(sentences),batch_size):
      batch_start, batch_end = i, min(i+batch_size, len(sentences))
      sent_lengths = [len(sent) for sent in sentences[batch_start:batch_end]]
      max_sent_length = max(sent_lengths)

      word_emb = np.zeros([len(sent_lengths), max_sent_length, self.embedding_size])
      for i, sent in enumerate(sentences[batch_start:batch_end]):
        for j, word in enumerate(sent):
          word_emb[i, j] = self.embedding_dict[word.lower()]

      word_ner_labels = np.zeros([len(sent_lengths), max_sent_length])
      gold_named_entities = set()
      for i, ner in enumerate(ners[batch_start:batch_end]):
        for s,e,l in ner:
          l_id = self.ner_labels_mappings[l]
          gold_named_entities.add((i,s,e,l_id))
          for j in range(s,e+1):
            word_ner_labels[i,j] = l_id


      feed_dict_list.append((
        word_emb,
        word_ner_labels,
        gold_named_entities,
        sent_lengths
      ))

    return feed_dict_list


  def batch_generator(self, fd_list):
    random.shuffle(fd_list)
    for word_embeddings, word_ner_labels, _, _ in fd_list:
      yield [word_embeddings], word_ner_labels

  def train(self, train_path, dev_path, test_path, epochs,batch_size=100):
    train_fd_list = self.get_feed_dict_list(train_path,batch_size)
    print("Load {} training batches from {}".format(len(train_fd_list), train_path))

    dev_fd_list = self.get_feed_dict_list(dev_path,batch_size)
    print("Load {} dev batches from {}".format(len(dev_fd_list), dev_path))

    test_fd_list = self.get_feed_dict_list(test_path,batch_size)
    print("Load {} test batches from {}".format(len(test_fd_list), test_path))

    start_time = time.time()
    for epoch in range(epochs):
      print("\nStarting training epoch {}/{}".format(epoch + 1, epochs))
      epoch_time = time.time()

      self.model.fit(self.batch_generator(train_fd_list), steps_per_epoch=len(train_fd_list))

      print("Time used for epoch {}: {}".format(epoch + 1, self.time_used(epoch_time)))
      dev_time = time.time()
      print("Evaluating on dev set after epoch {}/{}:".format(epoch + 1, epochs))
      self.eval(dev_fd_list)
      print("Time used for evaluate on dev set: {}".format(self.time_used(dev_time)))

    print("\nTraining finished!")
    print("Time used for training: {}".format(self.time_used(start_time)))

    print("\nEvaluating on test set:")
    test_time = time.time()
    self.eval(test_fd_list)
    print("Time used for evaluate on test set: {}".format(self.time_used(test_time)))

  def eval(self, eval_fd_list):
    tp, fn, fp = 0,0,0
    for word_embeddings, _, gold,sent_lens in eval_fd_list:
      predictions = self.model.predict_on_batch([word_embeddings])

      """
      Task 2 create the predictions of NER from the IO label 
      e.g. 
      0 I         O
      1 met       O
      2 John      PER
      3 this      O
      4 afternoon O
      should give you a person NE John (x,2,2,1)
      where x is the sentence id in the batch, and 2,2 are the start and end indices of the NE,
      1 is the id for 'PER'    
      """
      ner_labels_predicted = np.argmax(predictions, axis = 2)
      pred_set = set()
      for i, sent in enumerate(ner_labels_predicted):
        ner_end = 0
        ner_begin = 0
        sent = np.append(sent,0)
        for j, word in enumerate(sent):
          if ner_end != word and ner_end == 0 :
            ner_begin = j
          elif ner_end != 0 and ner_end != word:
            pred_set.add((i,ner_begin, j-1, int(ner_end)))
            ner_end = 0
            if word != 0:
              ner_begin=j
              ner_end = word
            continue
          ner_end = word
      tp += len(gold.intersection(pred_set))
      fp += len(pred_set.difference(gold))
      fn += len(gold.difference(pred_set))
      """
      End Task 2
      """

    p = 0.0 if tp == 0 else tp*1.0/(tp+fp)
    r = 0.0 if tp == 0 else tp*1.0/(tp+fn)
    f = 0.0 if tp == 0 else 2*p*r/(p+r)
    print("F1 : {:.2f}%".format(f * 100))
    print("Precision: {:.2f}%".format(p * 100))
    print("Recall: {:.2f}%".format(r * 100))

  def time_used(self, start_time):
    curr_time = time.time()
    used_time = curr_time - start_time
    m = used_time // 60
    s = used_time - 60 * m
    return "%d m %d s" % (m, s)

if __name__ == '__main__':
  embedding_path = 'glove.6B.100d.txt.ner.filtered'
  train_path = 'train.conll03.json'
  dev_path = 'dev.conll03.json'
  test_path = 'test.conll03.json'
  ner_labels = ['O', 'PER', 'ORG', 'LOC', 'MISC']
  embedding_size = 100
  model = NERModel(embedding_path,embedding_size, ner_labels)
  model.build()
  model.train(train_path,dev_path,test_path,5)