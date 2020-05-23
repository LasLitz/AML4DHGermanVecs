import math
from enum import Enum
from typing import Tuple

import gensim
from tqdm import tqdm

from evaluation_resource import NDFEvaluator
from UMLS import UMLSMapper, UMLSEvaluator
from embeddings import Embeddings
from abc import ABC, abstractmethod


class AbstractBenchmark(ABC):
    def __init__(self, embeddings: gensim.models.KeyedVectors,
                 umls_mapper: UMLSMapper,
                 umls_evaluator: UMLSEvaluator = None):
        self.embeddings = embeddings
        self.umls_mapper = umls_mapper
        self.umls_evaluator = umls_evaluator

    @abstractmethod
    def evaluate(self):
        pass

    def cosine(self, word1=None, word2=None, c1=None, c2=None):

        if word1:
            cos = self.embeddings.similarity(self.umls_mapper.umls_dict[word1], self.umls_mapper.umls_dict[word2])
        else:
            cos = self.embeddings.similarity(c1, c2)
        if cos < 0:
            return -cos
        else:
            return cos


class CategoryBenchmark(AbstractBenchmark):
    def __init__(self, embeddings: gensim.models.KeyedVectors, umls_mapper: UMLSMapper, umls_evaluator: UMLSEvaluator):
        super().__init__(embeddings=embeddings, umls_mapper=umls_mapper, umls_evaluator=umls_evaluator)

    def evaluate(self):
        print(self.all_categories_benchmark())

    def pairwise_cosine(self, concepts1, concepts2=None):
        if concepts2 is None:
            concepts2 = concepts1
            s = 0
            count = 0
            for i, concept1 in enumerate(concepts1):
                for j, concept2 in enumerate(concepts2):
                    if j > i:
                        c = self.cosine(c1=concept1, c2=concept2)
                        if c < 0:
                            c = -c
                        s += c
                        count += 1

            return s / count
        else:
            s = 0
            count = 0
            for i, concept1 in enumerate(concepts1):
                for j, concept2 in enumerate(concepts2):
                    c = self.cosine(c1=concept1, c2=concept2)
                    if c < 0:
                        c = -c
                    s += c
                    count += 1
            return s / count

    def category_benchmark(self, choosen_category):
        other_categories = self.umls_evaluator.category2concepts.keys()
        choosen_concepts = self.umls_evaluator.category2concepts[choosen_category]
        if len(choosen_concepts) <= 1:
            return 0, 0, 0
        p1 = self.pairwise_cosine(choosen_concepts)

        p2s = []
        for other_category in other_categories:
            if other_category == choosen_category:
                continue

            other_concepts = self.umls_evaluator.category2concepts[other_category]
            if len(choosen_concepts) == 0 or len(other_concepts) == 0:
                continue
            p2 = self.pairwise_cosine(choosen_concepts, other_concepts)
            p2s.append(p2)

        avg_p2 = sum(p2s) / len(p2s)
        return p1, avg_p2, p1 - avg_p2

    def all_categories_benchmark(self):

        distances = []
        categories = tqdm(self.umls_evaluator.category2concepts.keys())
        for category in categories:
            within, out, distance = self.category_benchmark(category)
            distances.append(distance)
            categories.set_description(f"{category}: {within:.4f}|{out:.4f}|{distance:.4f}")
            categories.refresh()  # to show immediately the update

        benchmark_value = sum(distances) / len(distances)
        return benchmark_value


class SilhouetteCoefficient(AbstractBenchmark):
    def __init__(self, embeddings: gensim.models.KeyedVectors, umls_mapper: UMLSMapper, umls_evaluator: UMLSEvaluator):
        super().__init__(embeddings=embeddings, umls_mapper=umls_mapper, umls_evaluator=umls_evaluator)

    def evaluate(self):
        print(self.silhouette_coefficient())

    def silhouette(self, term, category):
        def mean_between_distance(datapoint, same_cluster):
            sigma_ai = 0
            for reference_point in same_cluster:
                if datapoint == reference_point:
                    continue
                sigma_ai += self.cosine(c1=datapoint, c2=reference_point)

            return sigma_ai / (len(same_cluster) - 1)

        def smallest_mean_out_distance(datapoint, other_clusters):
            distances = []
            for other_cluster in other_clusters:
                sigma_bi = 0
                for other_reference_point in other_cluster:
                    sigma_bi += self.cosine(c1=datapoint, c2=other_reference_point)
                sigma_bi = sigma_bi / len(other_cluster)
                distances.append(sigma_bi)
            # return sum(distances)/len(distances) # alternative?
            return min(distances)

        cluster = self.umls_evaluator.category2concepts[category]
        other_cluster_names = set(self.umls_evaluator.category2concepts.keys()).difference(category)
        other_clusters = [self.umls_evaluator.category2concepts[category] for category in other_cluster_names]

        a_i = mean_between_distance(term, cluster)
        b_i = smallest_mean_out_distance(term, other_clusters)

        if a_i < b_i:
            s_i = 1 - a_i / b_i
        elif a_i == b_i:
            s_i = 0
        else:
            s_i = b_i / a_i - 1

        return s_i

    def silhouette_coefficient(self):
        s_is = []
        categories = tqdm(self.umls_evaluator.category2concepts.keys())
        for category in categories:
            category_concepts = self.umls_evaluator.category2concepts[category]
            if len(category_concepts) < 2:
                continue

            category_s_is = []
            for term in category_concepts:
                category_s_is.append(self.silhouette(term, category))

            mean_category_s_i = sum(category_s_is) / len(category_s_is)
            s_is.append(mean_category_s_i)
            categories.set_description(f"{category}: {mean_category_s_i:.4f}")
            categories.refresh()  # to show immediately the update
        return max(s_is)  # min, avg?

class EmbeddingSilhouetteCoefficient(AbstractBenchmark):
    def __init__(self, embeddings: gensim.models.KeyedVectors, umls_mapper: UMLSMapper, umls_evaluator: UMLSEvaluator):
        super().__init__(embeddings=embeddings, umls_mapper=umls_mapper, umls_evaluator=umls_evaluator)

    def evaluate(self):
        print(self.silhouette_coefficient())

    def silhouette(self, term, category):
        def mean_between_distance(datapoint, same_cluster):
            sigma_ai = 0
            for reference_point in same_cluster:
                if datapoint == reference_point:
                    continue
                sigma_ai += self.cosine(c1=datapoint, c2=reference_point)

            return sigma_ai / (len(same_cluster) - 1)

        def smallest_mean_out_distance(datapoint, other_clusters):
            distances = []
            for other_cluster in other_clusters:
                sigma_bi = 0
                for other_reference_point in other_cluster:
                    sigma_bi += self.cosine(c1=datapoint, c2=other_reference_point)
                sigma_bi = sigma_bi / len(other_cluster)
                distances.append(sigma_bi)
            # return sum(distances)/len(distances) # alternative?
            return sum(distances)/len(distances)

        cluster = self.umls_evaluator.category2concepts[category]
        other_cluster_names = set(self.umls_evaluator.category2concepts.keys()).difference(category)
        other_clusters = [self.umls_evaluator.category2concepts[category] for category in other_cluster_names]

        a_i = mean_between_distance(term, cluster)
        b_i = smallest_mean_out_distance(term, other_clusters)

        if a_i < b_i:
            s_i = 1 - a_i / b_i
        elif a_i == b_i:
            s_i = 0
        else:
            s_i = b_i / a_i - 1

        return s_i

    def silhouette_coefficient(self):
        s_is = []
        categories = tqdm(self.umls_evaluator.category2concepts.keys())
        for category in categories:
            category_concepts = self.umls_evaluator.category2concepts[category]
            if len(category_concepts) < 2:
                continue

            category_s_is = []
            for term in category_concepts:
                category_s_is.append(self.silhouette(term, category))

            mean_category_s_i = sum(category_s_is) / len(category_s_is)
            s_is.append(mean_category_s_i)
            categories.set_description(f"{category}: {mean_category_s_i:.4f}")
            categories.refresh()  # to show immediately the update
        return sum(s_is)/len(s_is)  # min, max?


class Relation(Enum):
    MAY_TREAT = "may_treat"
    MAY_PREVENT = "may_prevent"


class ChoiBenchmark(AbstractBenchmark):
    def __init__(self, embeddings: gensim.models.KeyedVectors,
                 umls_mapper: UMLSMapper,
                 ndf_evaluator: NDFEvaluator):
        super().__init__(embeddings=embeddings, umls_mapper=umls_mapper)
        self.ndf_evaluator = ndf_evaluator

    def evaluate(self):
        categories = ['Pharmacologic Substance',
                      'Disease or Syndrome',
                      'Neoplastic Process',
                      'Clinical Drug',
                      'Finding',
                      'Injury or Poisoning'
                      ]

        # for category in categories:
        #     print(f'{category}: {self.mcsm(category)}')
        relations =[
            Relation.MAY_TREAT,
            Relation.MAY_PREVENT
        ]
        for relation in relations:
            mean, max_value = self.run_mrm(relation=relation)
            print(f'{relation} - mean: {mean}, max: {max_value}')


    def mcsm(self, category, k=40):
        def category_true(concept, category):
            if category in self.umls_evaluator.concept2category[concept]:
                return 1
            else:
                return 0

        v_t = self.umls_evaluator.category2concepts[category]
        if len(v_t) == 0:
            return 0

        sigma = 0
        for v in v_t:
            for i in range(0, k):
                neighbors = self.embeddings.most_similar(v, topn=k)
                v_i = neighbors[i][0]
                sigma += category_true(v_i, category) / math.log((i + 1) + 1, 2)
        return sigma / len(v_t)

    def mrm(self, relation_dictionary, relation_dictionary_reversed, v_star, seed_pair: Tuple[str, str] = None, k=40):
        def relation_true(selected_concept, concepts):
            for concept in concepts:
                related_terms = relation_dictionary.get(selected_concept)
                if related_terms and concept in related_terms:
                    return 1

                inverse_related_terms = relation_dictionary_reversed.get(selected_concept)
                if inverse_related_terms and concept in inverse_related_terms:
                    return 1
            return 0

        def get_seed_pair():
            for key, values in relation_dictionary.items():
                if key in v_star:
                    for value in values:
                        if value in v_star:
                            return key, value

            return self.umls_mapper.umls_dict["Cisplatin"], self.umls_mapper.umls_dict["Carboplatin"]

        # if relation == Relation.MAY_TREAT:
        #     relation_dictionary = self.ndf_evaluator.may_treat
        #     relation_dictionary_reversed = self.ndf_evaluator.reverted_treat
        # else:
        #     relation_dictionary = self.ndf_evaluator.may_prevent
        #     relation_dictionary_reversed = self.ndf_evaluator.reverted_prevent
        #
        # v_star = set(relation_dictionary.keys())
        # v_star.update(relation_dictionary_reversed.keys())
        # v_star = [concept for concept in v_star if concept in self.embeddings.vocab]

        if seed_pair is None:
            seed_pair = get_seed_pair()

        # print(seed_pair)
        s = self.embeddings.get_vector(seed_pair[0]) - self.embeddings.get_vector(seed_pair[1])

        sigma = 0

        for v in v_star:
            neighbors = self.embeddings.most_similar(positive=[self.embeddings.get_vector(v)-s], topn=k)
            neighbors = [tupl[0] for tupl in neighbors]

            sigma += relation_true(selected_concept=v, concepts=neighbors)
        return sigma / len(v_star)

    def run_mrm(self, relation: Relation):

        if relation == Relation.MAY_TREAT:
            relation_dict = self.ndf_evaluator.may_treat
            relation_dict_reversed = self.ndf_evaluator.reverted_treat
        else:
            relation_dict = self.ndf_evaluator.may_prevent
            relation_dict_reversed = self.ndf_evaluator.reverted_prevent

        v_star = set(relation_dict.keys())
        v_star.update(relation_dict_reversed.keys())
        v_star = [concept for concept in v_star if concept in self.embeddings.vocab]

        results = []
        tqdm_progress = tqdm(relation_dict.items(), total=len(relation_dict.keys()))
        for key, values in tqdm_progress:
            if key in v_star:
                for value in values:
                    if value in v_star:
                        results.append(self.mrm(relation_dict, relation_dict_reversed, v_star,
                                                seed_pair=(key, value), k=40))
                        tqdm_progress.set_description(f'{key}: [{results[-1]:.5f}, {sum(results) / len(results):.5f}, {max(results):.5f}]')
                        tqdm_progress.update()


        return sum(results)/len(results), max(results)


class Evaluation:
    def __init__(self, embeddings: gensim.models.KeyedVectors,
                 umls_mapper: UMLSMapper,
                 umls_evaluator: UMLSEvaluator,
                 ndf_evaluator: NDFEvaluator):
        self.benchmarks = [
            # CategoryBenchmark(embeddings, umls_mapper, umls_evaluator),
            # SilhouetteCoefficient(embeddings, umls_mapper, umls_evaluator),
            ChoiBenchmark(embeddings, umls_mapper, ndf_evaluator)
        ]

    def evaluate(self):
        for benchmark in self.benchmarks:
            print(benchmark.__class__.__name__)
            benchmark.evaluate()


def analogies(vectors, start, minus, plus, umls: UMLSMapper):
    if umls:
        return vectors.most_similar(positive=[umls.umls_dict[start], umls.umls_dict[plus]],
                                    negative=[umls.umls_dict[minus]])
    else:
        return vectors.most_similar(positive=[start, plus], negative=[minus])


def similarities(vectors, word, umls):
    if umls:
        return vectors.most_similar(umls.umls_dict[word])
    else:
        return vectors.most_similar(word)


def main():
    umls_mapper = UMLSMapper(from_dir='E:/AML4DH-DATA/UMLS')
    vecs = Embeddings.load(path="data/no_prep_vecs_test_all.kv")
    umls_evaluator = None # UMLSEvaluator(from_dir='E:/AML4DH-DATA/UMLS', vectors=vecs)
    ndf_evaluator = NDFEvaluator(from_dir="E:/AML4DH-DATA/NDF")

    # for c, v in vecs.most_similar("Cisplatin"):
    #     print(umls_mapper.un_umls(c), v)
    #
    #
    # # for c, v in vecs.most_similar(umls_mapper.umls_dict["Cisplatin"]):
    # #     print(umls_mapper.un_umls(c), v)
    #
    # for c, v in analogies(vecs, "Asthma", "Lunge", "Herz", umls=umls_mapper):
    #     print(umls_mapper.un_umls(c), v)
    #
    # for c, v in similarities(vecs, "Hepatitis", umls=umls_mapper):
    #     print(umls_mapper.un_umls(c), v)
    #
    # for c, v in similarities(vecs, "Cisplatin", umls=umls_mapper):
    #     print(umls_mapper.un_umls(c), v)

    # print([(umls_mapper.un_umls(c), Embedding(umls_mapper.un_umls(c), vecs[c])) for c in vecs.vocab])

    # benchmark = CategoryBenchmark(vecs, umls_mapper, evaluator)
    # benchmark.evaluate()

    eval = Evaluation(vecs, umls_mapper, umls_evaluator, ndf_evaluator)
    eval.evaluate()

    # benchmark.category_benchmark("Nucleotide Sequence")

    # emb = EmbeddingSet( {umls_mapper.un_umls(c, single_return=True): Embedding(umls_mapper.un_umls(c,
    # single_return=True), vecs[c]) for c in vecs.vocab}) # emb = EmbeddingSet({c: Embedding(c, vecs[c]) for c in
    # vecs.vocab})
    #
    # emb.plot_interactive("Fibroblasten", "Fremdkörper")

    # replace multi words


if __name__ == "__main__":
    main()
