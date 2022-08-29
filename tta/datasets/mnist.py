# Forked from https://github.com/facebookresearch/DomainBed/blob/main/domainbed/datasets.py
import numpy as np
import torch
from torch.utils.data import TensorDataset
from torchvision.datasets import MNIST
from torchvision import transforms as T
from PIL import Image

from . import MultipleDomainDataset


class MultipleDomainMNIST(MultipleDomainDataset):
    colors = torch.ByteTensor([
        (1, 0, 0),
        (0, 1, 0),
    ])

    angles = [0, 15]

    environments = [0.9, 0.8, 0.1]

    def __init__(self, root, generator):
        input_shape = (1, 28, 28, 3)
        super().__init__(input_shape)

        if root is None:
            raise ValueError('Data directory not specified!')

        self.generator = generator

        original_dataset_tr = MNIST(root, train=True, download=False)
        original_dataset_te = MNIST(root, train=False, download=False)

        original_images = torch.cat((original_dataset_tr.data,
                                     original_dataset_te.data))

        original_labels = torch.cat((original_dataset_tr.targets,
                                     original_dataset_te.targets))

        shuffle = torch.randperm(len(original_images), generator=generator)

        original_images = original_images[shuffle]
        original_labels = original_labels[shuffle]

        self.Z = torch.LongTensor([(c_idx, r_idx) for c_idx in range(len(self.colors)) for r_idx in range(len(self.angles))])

        # joint distribution of Y and Z
        num_categories = 10
        num_classes = len(self.Z)
        independent = np.ones((num_categories, num_classes)) * 1/num_classes

        confounding1 = np.zeros((num_categories, num_classes))
        idx = torch.randint(0, num_classes, (num_categories,), generator=self.generator)
        confounding1[torch.arange(num_categories), idx] = 1
        confounding1 = 0.9 * confounding1 + 0.1 * independent

        confounding2 = np.zeros((num_categories, num_classes))
        idx = torch.randint(0, num_classes, (num_categories,), generator=self.generator)
        confounding2[torch.arange(num_categories), idx] = 1
        confounding2 = 0.9 * confounding2 + 0.1 * independent

        for i, strength in enumerate(self.environments):
            images = original_images[i::len(self.environments)]
            labels = original_labels[i::len(self.environments)]
            marginal = torch.from_numpy(strength * confounding1 + (1-strength) * confounding2)
            domain = self.shift(images, labels, marginal)

            joint = torch.zeros_like(marginal)
            for label in labels:
                joint[label] += marginal[label]
            joint /= len(labels)
            self.domains.append((joint, domain))


    def shift(self, images, labels, marginal):
        lookup_table = torch.cumsum(marginal, dim=1)
        to_tensor = T.ToTensor()
        N = labels.size(0)

        # inject noise to Y
        weights = torch.ones((N, 10))
        weights[torch.arange(N), labels] += 80
        y = torch.multinomial(weights, 1, generator=self.generator).squeeze(dim=-1)

        # generate Z condition on Y
        values = torch.rand((N, 1), generator=self.generator)
        z_idx = torch.searchsorted(lookup_table[labels], values).squeeze(dim=-1)
        z = self.Z[z_idx]
        z_flattened = len(self.angles) * z[:, 0] + z[:, 1]

        # transform X based on Z
        x = torch.zeros(N, 28, 28, 3)
        for i, (image, (color_idx, angle_idx)) in enumerate(zip(images, z)):
            color = self.colors[color_idx]
            angle = self.angles[angle_idx]

            image = color * image.unsqueeze(-1)
            image = Image.fromarray(image.numpy())
            image = image.rotate(angle, resample=Image.BILINEAR, fillcolor=tuple(color.tolist()))
            image = to_tensor(image)
            image = image.permute(1, 2, 0)

            x[i] = image

        return TensorDataset(x, y, z_flattened)
