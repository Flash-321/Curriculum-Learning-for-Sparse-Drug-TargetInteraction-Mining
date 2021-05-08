from torch.utils.data import Dataset
import pickle as pkl
import pysmiles
import json
import numpy as np
import logging
import sys
sys.path.append("..")
from utils.protein_embedding import *

logging.getLogger('pysmiles').setLevel(logging.CRITICAL)
logger = logging.getLogger('Data')

MAX_NODE_SIZE = 629


class DrugDataset(Dataset):
    def __init__(self, dataset, datadir, edge_weight=True, use_hcount=True, **kwargs):
        """
        :arg
            edge_weight:
                False - returns binary matrix, 1 for adjacent, 0 for not.
                True - use edge order to weight the matrix
            use_hcount:
                False - only use element of each node to embed node
                True - add extra hydrogens count info
        """
        super(DrugDataset, self).__init__()
        self.edge_weight = edge_weight
        self.use_hcount = use_hcount
        self.data = pkl.load(open(datadir + "/" + dataset + '/drug.pkl', 'rb'))

        element = json.load(open(datadir + "/" + dataset + '/element.json'))
        hcount = json.load(open(datadir + "/" + dataset + '/hcount.json'))

        self.element2idx = {ele: i for i, ele in enumerate(element)}
        self.hcount2idx = {count: i for i, count in enumerate(hcount)}

        if use_hcount:
            self.embedding_dim = len(self.element2idx) + len(self.hcount2idx)
        else:
            self.embedding_dim = len(self.element2idx)

        print('Load Drug Dataset Complete')

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        smile_str = self.data[index]
        graph = pysmiles.read_smiles(smile_str)

        node_embedding = np.zeros([MAX_NODE_SIZE, self.embedding_dim])
        for node_id, node_info in graph.nodes.data():
            element = node_info['element']
            hcount = node_info['hcount']
            node_embedding[node_id, self.element2idx[element]] = 1
            if self.use_hcount:
                node_embedding[node_id, self.hcount2idx[hcount]] = 1

        padding_mask = (node_embedding.sum(1) == 0).astype(float)

        adjacent_matrix = np.zeros([MAX_NODE_SIZE, MAX_NODE_SIZE])
        for a, b, edge_info in graph.edges.data():
            val = edge_info['order'] if self.edge_weight else 1
            adjacent_matrix[a, b] = val
            adjacent_matrix[b, a] = val

        drug = (node_embedding, adjacent_matrix, padding_mask)
        return drug


class TargetDataset(Dataset):
    def __init__(self, dataset, datadir, pretrained_dir, device, **kwargs):
        super(TargetDataset, self).__init__()
        self.data = pkl.load(open(datadir + "/" + dataset + '/target.pkl', 'rb'))
        self.device = device
        lm = BiLM(nin=22, embedding_dim=21, hidden_dim=1024, num_layers=2, nout=21)
        model_ = StackedRNN(nin=21, nembed=512, nunits=512, nout=100, nlayers=3, padding_idx=20, dropout=0, lm=lm)
        model = OrdinalRegression(embedding=model_, n_classes=5)
        tmp = torch.load(pretrained_dir)
        model.load_state_dict(tmp)
        model = load_model(model, device=device)
        self.model = model
        print('Load Target Dataset Complete')
        return

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        protein_string = self.data[index]
        protein_string = bytes(protein_string, encoding='utf8')
        import time
        s = time.time()
        protein_embedding = embedding(protein_string, self.model, self.device)
        print(time.time()-s)
        return protein_embedding


class DrugTargetInteractionDataset(Dataset):
    def __init__(self, dataset, datadir, stepSize, pretrained_dir, device, **kwargs):
        super(DrugTargetInteractionDataset, self).__init__()
        self.pairs = pkl.load(open(datadir + "/" + dataset + '/pairs.pkl', 'rb'))
        self.dataset = dataset
        self.stepSize = stepSize
        self.drug_dataset = DrugDataset(dataset, datadir, **kwargs)
        self.target_dataset = TargetDataset(dataset, datadir, pretrained_dir, device, **kwargs)
        print('Load DTI Dataset Complete')
        return

    def __getitem__(self, index):
        if self.dataset == "train":
            # index goes from 0 to stepSize-1
            # dividing the dataset into partitions of size equal to stepSize and selecting a random partition
            # fetch the sample at position 'index' in this randomly selected partition
            base = self.stepSize * np.arange(int(len(self.pairs) / self.stepSize) + 1)
            ixs = base + index
            ixs = ixs[ixs < len(self.pairs)]
            index = ixs[0] if len(ixs) == 1 else np.random.choice(ixs)

        drug_idx, target_idx, label = self.pairs[index]
        return self.drug_dataset[drug_idx], self.target_dataset[target_idx], label

    def __len__(self):
        if self.dataset == "train":
            return self.stepSize
        else:
            return len(self.pairs)
