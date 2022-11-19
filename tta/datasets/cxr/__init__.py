import numpy as np
from scipy.special import softmax
import torch
from torch.utils.data import TensorDataset

from tta.datasets import MultipleDomainDataset


class MultipleDomainCXR(MultipleDomainDataset):

    def build(self, generator, datastore, labels, Y_col, Z_col, patient_col, anchor1, anchor2, target_domain_count):
        mask = np.ones(len(labels.index), dtype=bool)
        domains = [None for _ in self.confounder_strength]

        # Sample source domains
        for i, strength in enumerate(self.confounder_strength):
            if i != self.train_domain:
                continue

            quota = labels["M"].loc[mask].value_counts().sort_index().values - target_domain_count
            quota = torch.from_numpy(quota)
            joint_M = torch.from_numpy(strength * anchor1 + (1-strength) * anchor2)
            joint_M_flatten = joint_M.flatten()
            count = torch.round(torch.min(quota/joint_M_flatten)*joint_M_flatten).long()
            count = count.reshape((2, 2))
            joint_M = count / torch.sum(count)

            print(f"histogram(M) = {count.flatten()}")
            reservation = np.ceil(target_domain_count * np.maximum(anchor1, anchor2).flatten())
            domain, in_sample_patients = self.sample(generator, datastore, labels, Y_col, Z_col, patient_col, mask, count, reservation)
            mask &= ~labels[patient_col].isin(in_sample_patients)
            domains[i] = (joint_M, domain)

        remainder = np.sum(mask)
        if remainder < target_domain_count:
            raise ValueError(f"Not enough data for target domains: {remainder} < {target_domain_count}")

        # Sample target domains
        for i, strength in enumerate(self.confounder_strength):
            if i == self.train_domain:
                continue

            joint_M = torch.from_numpy(strength * anchor1 + (1-strength) * anchor2)
            joint_M_flatten = joint_M.flatten()
            count = torch.round(target_domain_count * joint_M_flatten).long()

            l1, l2, l3 = torch.topk(count, 3).indices
            if torch.sum(count) > target_domain_count:
                count[l1] -= 1
            if torch.sum(count) > target_domain_count:
                count[l2] -= 1
            if torch.sum(count) > target_domain_count:
                count[l3] -= 1

            s1, s2, s3 = torch.topk(count, 3, largest=False).indices
            if torch.sum(count) < target_domain_count:
                count[s1] += 1
            if torch.sum(count) < target_domain_count:
                count[s2] += 1
            if torch.sum(count) < target_domain_count:
                count[s3] += 1

            total_count = torch.sum(count)
            assert total_count == target_domain_count, f"Incorrect total count: {total_count} != {target_domain_count}"

            count = count.reshape((2, 2))
            joint_M = count / torch.sum(count)

            print(f"histogram(M) = {count.flatten()}")
            domain, _ = self.sample(generator, datastore, labels, Y_col, Z_col, patient_col, mask, count, None)
            domains[i] = (joint_M, domain)

        return domains


    def sample(self, generator, datastore, labels, Y_col, Z_col, patient_col, mask, count, reservation):
        random_state = 0
        while True:
            in_sample = set()
            for Y in range(2):
                for Z in range(2):
                    masked = labels.loc[mask & (labels["M"] == 2 * Y + Z)]
                    image_per_patient = masked.groupby(patient_col).size()
                    weights = softmax(image_per_patient.loc[masked[patient_col]].values)
                    indices = masked.sample(int(count[Y, Z]), weights=weights, random_state=random_state)
                    in_sample.update(indices.index)

            class_name = self.__class__.__name__
            if class_name == "MultipleDomainCheXpert":
                in_sample_patients = { fname.split("/")[2] for fname in in_sample }
            elif class_name == "MultipleDomainMIMIC":
                subject_id = labels["subject_id"]
                in_sample_patients = { subject_id.loc[dicom_id] for dicom_id in in_sample }
            else:
                raise NotImplementedError(f"Unknown dataset {class_name}")

            remainder = np.bincount(labels["M"], weights=mask & ~labels[patient_col].isin(in_sample_patients))
            if reservation is None or np.all(remainder >= reservation):
                print(f"  remainder = {remainder} >= {reservation} = target_domain_count")
                break

            random_state += 1
            print(f"  remainder = {remainder} < {reservation} = target_domain_count")

        N = int(torch.sum(count))
        assert len(in_sample) == N, f"Incorrect number of elements: {len(in_sample)} != {N}"

        x = torch.empty((N, *self.input_shape[1:]))
        y_tilde = torch.empty(N, dtype=torch.long)
        y = torch.empty(N, dtype=torch.long)
        z_flattened = torch.empty(N, dtype=torch.long)

        perm = torch.randperm(N, generator=generator)
        for i, key in enumerate(in_sample):
            x[perm[i]] = torch.Tensor(datastore[key])
            row = labels.loc[key]
            y[perm[i]] = y_tilde[perm[i]] = row[Y_col]
            z_flattened[perm[i]] = row[Z_col]

        return TensorDataset(x, y_tilde, y, z_flattened), in_sample_patients
