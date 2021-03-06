import math
import random
from abc import ABC, abstractmethod
from collections import defaultdict
from enum import Enum
from typing import Tuple, Dict, Set, Iterable, List, Union
import numpy as np
from gensim import matutils
from scipy.stats.mstats import spearmanr
from tqdm import tqdm

from benchmarking import constant
from resource.UMLS import UMLSMapper, UMLSEvaluator, MRRELEvaluator
from resource.other_resources import NDFEvaluator, SRSEvaluator, Evaluator
from joblib import Parallel, delayed
import multiprocessing

from vectorization.embeddings import Embedding


def revert_list_dict(dictionary: Dict[str, Set[str]], filter_collection: Iterable = None) -> Dict[str, Set[str]]:
    reverted_dictionary = defaultdict(set)
    for key, values in dictionary.items():
        for value in values:
            if not filter_collection or value in filter_collection:
                reverted_dictionary[value].add(key)
    return reverted_dictionary


class Benchmark(ABC):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper):
        self.vectors = embedding.vectors
        self.dataset = embedding.dataset
        self.algorithm = embedding.algorithm
        self.preprocessing = embedding.preprocessing
        try:
            self.vocab = self.vectors.vocab
        except AttributeError:
            self.vocab = self.vectors.vocabulary
        self.umls_mapper = umls_mapper

        self.oov_embedding = None

    @abstractmethod
    def evaluate(self) -> Union[float, Tuple[float, float]]:
        pass

    def clean(self):
        del self.vectors
        del self.vocab
        del self.dataset
        del self.algorithm
        del self.preprocessing

    def cosine(self, word1: str = None, word2: str = None,
               concept1: str = None, concept2: str = None,
               vector1: np.ndarray = None, vector2: np.ndarray = None,
               same_vec_zero: bool = False) -> Union[float, None]:
        cos = None

        if word1 and word2:
            cos = self.vectors.similarity(self.umls_mapper.umls_dict[word1], self.umls_mapper.umls_dict[word2])

        if concept1 and concept2:
            if concept1 in self.vocab and concept2 in self.vocab:
                cos = self.vectors.similarity(concept1, concept2)
            else:

                vector1 = self.get_concept_vector(concept1)
                vector2 = self.get_concept_vector(concept2)
                # print(concept1, concept2, vector1, vector2)

        if vector1 is not None and vector2 is not None:
            if same_vec_zero and (vector1 == vector2).all():
                cos = 0
            else:
                cos = self.vectors.cosine_similarities(vector1, np.array([vector2]))[0]

        if np.isnan(cos):
            cos = 0
        if cos:
            cos = -cos if cos < 0 else cos
        return cos

    def similarity_matrix(self, vectors: List[np.ndarray]) -> np.ndarray:
        matrix = []
        for vector_1 in tqdm(vectors, total=len(vectors)):
            row = []
            for vector_2 in vectors:
                row.append(self.cosine(vector1=vector_1, vector2=vector_2))
            matrix.append(np.array(row))
        return np.array(matrix)

    @staticmethod
    def n_similarity(v1: Union[List[np.ndarray], np.ndarray], v2: Union[List[np.ndarray], np.ndarray]) -> np.ndarray:
        if isinstance(v1, list):
            v1 = np.array(v1)
        if isinstance(v2, list):
            v2 = np.array(v2)
        if not (len(v1) and len(v2)):
            raise ZeroDivisionError('At least one of the passed lists is empty.')
        return np.dot(matutils.unitvec(v1.mean(axis=0)), matutils.unitvec(v2.mean(axis=0)))

    def avg_embedding(self) -> np.ndarray:
        # def nan_checker(inp):
        #     if np.isnan(inp) or inp == np.nan:
        #         return 0
        #     else:
        #         return inp
        if self.oov_embedding is None:
            vecs = [self.vectors.get_vector(word) for word in self.vocab]
            # vecs = [np.array([nan_checker(ele) for ele in vec]) for vec in vecs]
            self.oov_embedding = sum(vecs) / len(vecs)
        return self.oov_embedding

    def get_concept_vector_old(self, concept) -> Union[np.ndarray, None]:
        if concept in self.vocab:
            # print("in", concept,  self.umls_mapper.umls_reverse_dict[concept])
            return self.vectors.get_vector(concept)
        else:
            if concept in self.umls_mapper.umls_reverse_dict:
                concept_vectors = []
                for candidate in self.umls_mapper.umls_reverse_dict[concept]:
                    candidate_tokens = candidate.split()
                    candidate_vectors = []
                    for token in candidate_tokens:
                        if token in self.vocab:
                            candidate_vectors.append(self.vectors.get_vector(token))

                    if len(candidate_vectors) == len(candidate_tokens):
                        candidate_vector = sum(candidate_vectors)
                        concept_vectors.append(candidate_vector)

                if len(concept_vectors) > 0:
                    concept_vector = sum(concept_vectors) / len(concept_vectors)
                    # print("not in", concept, self.umls_mapper.umls_reverse_dict[concept])
                    return concept_vector
            return None

    def get_concept_vector(self, concept, give_none: bool = False) -> Union[np.ndarray, None]:
        try:
            return self.vectors.get_vector(concept)
        except KeyError:
            if give_none:
                return None
            return self.avg_embedding()


class CategoryBenchmark(Benchmark):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator]):
        super().__init__(embedding=embedding, umls_mapper=umls_mapper)
        self.umls_evaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator

        self.concept2category = {concept: category for concept, category in self.umls_evaluator.concept2category.items()
                                 if concept in self.vocab}

        self.category2concepts = revert_list_dict(self.concept2category)

    def evaluate(self) -> float:
        score = self.all_categories_benchmark()
        return score

    def pairwise_cosine(self, concepts1, concepts2=None):
        if concepts2 is None:
            concepts2 = concepts1
            s = 0
            count = 0
            for i, concept1 in enumerate(concepts1):
                for j, concept2 in enumerate(concepts2):
                    if j > i:

                        cos_sim = self.cosine(concept1=concept1, concept2=concept2)
                        if cos_sim:
                            if cos_sim < 0:
                                cos_sim = -cos_sim
                            s += cos_sim
                            count += 1

            return s / count
        else:
            s = 0
            count = 0
            for i, concept1 in enumerate(concepts1):
                for j, concept2 in enumerate(concepts2):
                    cos_sim = self.cosine(concept1=concept1, concept2=concept2)
                    if cos_sim < 0:
                        cos_sim = -cos_sim
                    s += cos_sim
                    count += 1
            return s / count

    def category_benchmark(self, choosen_category):
        other_categories = self.category2concepts.keys()
        choosen_concepts = self.category2concepts[choosen_category]
        if len(choosen_concepts) <= 1:
            return 0, 0, 0
        p1 = self.pairwise_cosine(choosen_concepts)

        p2s = []
        for other_category in other_categories:
            if other_category == choosen_category:
                continue

            other_concepts = self.category2concepts[other_category]
            if len(choosen_concepts) == 0 or len(other_concepts) == 0:
                continue
            p2 = self.pairwise_cosine(choosen_concepts, other_concepts)
            p2s.append(p2)

        avg_p2 = sum(p2s) / len(p2s)
        return p1, avg_p2, p1 - avg_p2

    def all_categories_benchmark(self):

        distances = []
        print(self.category2concepts.keys())
        categories = tqdm(self.category2concepts.keys())
        for category in categories:
            within, out, distance = self.category_benchmark(category)
            distances.append(distance)
            categories.set_description(f"{category}: {within:.4f}|{out:.4f}|{distance:.4f}")
            categories.refresh()  # to show immediately the update

        benchmark_value = sum(distances) / len(distances)
        return benchmark_value


class SilhouetteCoefficient(Benchmark):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator]):
        super().__init__(embedding=embedding, umls_mapper=umls_mapper)
        self.umls_evaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator

        self.concept2category = {concept: category for concept, category in self.umls_evaluator.concept2category.items()
                                 if concept in self.vocab}

        self.category2concepts = revert_list_dict(self.concept2category)

    def evaluate(self) -> float:
        score = self.silhouette_coefficient()
        return score

    def silhouette(self, term, category):
        def mean_between_distance(datapoint, same_cluster):
            sigma_ai = 0
            for reference_point in same_cluster:
                if datapoint == reference_point:
                    continue
                sigma_ai += self.cosine(concept1=datapoint, concept2=reference_point)

            return sigma_ai / (len(same_cluster) - 1)

        def smallest_mean_out_distance(datapoint, other_clusters):
            distances = []
            for other_cluster in other_clusters:
                sigma_bi = 0
                for other_reference_point in other_cluster:
                    sigma_bi += self.cosine(concept1=datapoint, concept2=other_reference_point)
                sigma_bi = sigma_bi / len(other_cluster)
                distances.append(sigma_bi)
            # return sum(distances)/len(distances) # alternative?
            return min(distances)

        cluster = self.category2concepts[category]
        other_cluster_names = set(self.category2concepts.keys()).difference(category)
        other_clusters_concepts = [self.category2concepts[category] for category in other_cluster_names]

        a_i = mean_between_distance(term, cluster)
        b_i = smallest_mean_out_distance(term, other_clusters_concepts)

        if a_i < b_i:
            s_i = 1 - a_i / b_i
        elif a_i == b_i:
            s_i = 0
        else:
            s_i = b_i / a_i - 1

        return s_i

    def silhouette_coefficient(self):
        s_is = []
        categories = tqdm(self.category2concepts.keys())
        for category in categories:
            category_concepts = self.category2concepts[category]
            if len(category_concepts) < 2:
                continue

            category_s_is = []
            for term in category_concepts:
                category_s_is.append(self.silhouette(term, category))

            mean_category_s_i = sum(category_s_is) / len(category_s_is)
            s_is.append(mean_category_s_i)
            categories.set_description(f"{category}: {mean_category_s_i:.4f}")
            categories.refresh()  # to show immediately the update
        if len(s_is) == 0:
            return 0
        return max(s_is)  # min, avg?


class EmbeddingSilhouetteCoefficient(Benchmark):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator]):
        super().__init__(embedding=embedding, umls_mapper=umls_mapper)
        self.umls_evaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator
        self.concept2category = {concept: category for concept, category in self.umls_evaluator.concept2category.items()
                                 if concept in self.vocab}

        self.category2concepts = revert_list_dict(self.concept2category)

    def evaluate(self):
        score = self.silhouette_coefficient()
        return score

    def silhouette(self, term, category):
        def mean_between_distance(datapoint, same_cluster):
            sigma_ai = 0
            for reference_point in same_cluster:
                if datapoint == reference_point:
                    continue
                sigma_ai += self.cosine(concept1=datapoint, concept2=reference_point)

            return sigma_ai / (len(same_cluster) - 1)

        def smallest_mean_out_distance(datapoint, other_clusters):
            distances = []
            for other_cluster in other_clusters:
                sigma_bi = 0
                for other_reference_point in other_cluster:
                    sigma_bi += self.cosine(concept1=datapoint, concept2=other_reference_point)
                sigma_bi = sigma_bi / len(other_cluster)
                distances.append(sigma_bi)
            # return sum(distances)/len(distances) # alternative?
            return sum(distances) / len(distances)

        cluster = self.category2concepts[category]
        other_cluster_names = set(self.category2concepts.keys()).difference(category)
        other_clusters_concepts = [self.category2concepts[category] for category in other_cluster_names]

        a_i = mean_between_distance(term, cluster)
        b_i = smallest_mean_out_distance(term, other_clusters_concepts)

        if a_i < b_i:
            s_i = 1 - a_i / b_i
        elif a_i == b_i:
            s_i = 0
        else:
            s_i = b_i / a_i - 1

        return s_i

    def silhouette_coefficient(self):
        s_is = []
        categories = tqdm(self.category2concepts.keys())
        for category in categories:
            category_concepts = self.category2concepts[category]
            if len(category_concepts) < 2:
                continue

            category_s_is = []
            for term in category_concepts:
                category_s_is.append(self.silhouette(term, category))

            mean_category_s_i = sum(category_s_is) / len(category_s_is)
            s_is.append(mean_category_s_i)
            categories.set_description(f"{category}: {mean_category_s_i:.4f}")
            categories.refresh()  # to show immediately the update
        if len(s_is) == 0:
            return 0
        return sum(s_is) / len(s_is)  # min, max?


class Relation(Enum):
    MAY_TREAT = "may_treat"
    MAY_PREVENT = "may_prevent"


class ConceptualSimilarityChoi(Benchmark):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator]):
        super().__init__(embedding=embedding, umls_mapper=umls_mapper)
        self.ndf_evaluator = None
        self.umls_evaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator
            if isinstance(evaluator, NDFEvaluator):
                self.ndf_evaluator = evaluator

        # for key, value in self.__dict__.items():
        #     if 'evaluator' in key.lower():
        #         if value is None:
        #             raise UserWarning(f"{key} not in list")

        self.concept2category = {concept: category for concept, category in self.umls_evaluator.concept2category.items()
                                 if concept in self.vocab}

        self.category2concepts = revert_list_dict(self.concept2category)

    def evaluate(self):
        categories = ['Pharmacologic Substance',
                      'Disease or Syndrome',
                      'Neoplastic Process',
                      'Clinical Drug',
                      'Finding',
                      'Injury or Poisoning',
                      ]

        results = []
        tqdm_bar = tqdm(categories)
        for category in tqdm_bar:
            category_result = self.mcsm(category)
            # print(f'{self.dataset}|{self.preprocessing}|{self.algorithm} [{category}]: {category_result}')
            results.append(category_result)
            tqdm_bar.set_description(f"Conceptual Similarity Choi ({self.dataset}|{self.algorithm}|"
                                     f"{self.preprocessing}): "
                                     f"{category_result:.4f}")
            tqdm_bar.update()
        return sum(results)/len(results)

    def mcsm(self, category, k=40):
        # V: self.concept2category.keys()
        # T: category
        # k: k
        # V(t): v_t = self.category2concepts[category]
        # 1T: category_true

        def category_true(concept_neighbor, semantic_category):
            if semantic_category in self.concept2category[concept_neighbor]:
                return 1
            else:
                return 0

        v_t = self.category2concepts[category]
        if len(v_t) == 0:
            return 0

        sigma = 0

        for v in v_t:
            neighbors = self.vectors.most_similar(v, topn=k)
            for i in range(0, k):
                v_i = neighbors[i][0]

                if v_i in self.concept2category:
                    sigma += category_true(v_i, category) / math.log((i + 1) + 1, 2)
                # else: sigma += 0 (if neighbor not CUI ignore it)

        if len(v_t) == 0:
            return 0
        return sigma / len(v_t)


class MedicalRelatednessChoi(Benchmark, ABC):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 relation: Relation,
                 evaluators: List[Evaluator]):
        super().__init__(embedding=embedding, umls_mapper=umls_mapper)
        self.ndf_evaluator = None
        self.umls_evaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator
            if isinstance(evaluator, NDFEvaluator):
                self.ndf_evaluator = evaluator

        self.concept2category = {concept: category for concept, category in self.umls_evaluator.concept2category.items()
                                 if concept in self.vocab}

        self.category2concepts = revert_list_dict(self.concept2category)
        self.relation = relation

    def evaluate(self):
        mean, max_value = self.run_mrm(relation=self.relation, sample=100)
        # print(f'{self.relation} - mean: {mean}, max: {max_value}')
        return mean, max_value

    def mrm(self, relation_dictionary, v_star, seed_pair: Tuple[str, str] = None,
            k=40):
        # V: self.concept2category.keys()
        # R: relation_dictionary, relation_dictionary_reversed
        # k: k
        # V*: v_star
        # with the given relation
        # V(t): v_t = self.category2concepts[category]
        # 1R: relation_true
        # s: seed_pair
        def relation_true(selected_concept, concepts):
            for concept in concepts:
                related_terms = relation_dictionary.get(selected_concept)
                if related_terms and concept in related_terms:
                    return 1

            return 0

        s_difference = self.get_concept_vector(seed_pair[0]) - self.get_concept_vector(seed_pair[1])

        def compute_neighbor_relations(v, v_vector, s, vectors):
            neighbors = vectors.most_similar(positive=[v_vector - s], topn=k)
            neighbors = [tupl[0] for tupl in neighbors]
            return relation_true(selected_concept=v, concepts=neighbors)

        num_cores = multiprocessing.cpu_count()
        results = Parallel(n_jobs=num_cores, backend="threading")(delayed(compute_neighbor_relations)
                                                                  (v_star_i, self.get_concept_vector(v_star_i),
                                                                   s_difference, self.vectors)
                                                                  for v_star_i in v_star)
        if len(v_star) == 0:
            return 0
        return sum(results) / len(v_star)

    def run_mrm(self, relation: Relation, sample: int = None):
        if relation == Relation.MAY_TREAT:
            relation_dict = self.ndf_evaluator.may_treat
            # relation_dict_reversed = self.ndf_evaluator.reverted_treat
        else:
            relation_dict = self.ndf_evaluator.may_prevent
            # relation_dict_reversed = self.ndf_evaluator.reverted_prevent

        v_star = set(relation_dict.keys())
        v_star = list(v_star)
        # v_star = [concept for concept in v_star if concept in self.vocab]

        seed_pairs = [(substance, disease) for substance, diseases in relation_dict.items() for disease in diseases]

        if sample:
            random.seed(42)
            seed_pairs = random.sample(seed_pairs, 100)

        tqdm_progress = tqdm(seed_pairs, total=len(seed_pairs))

        # results = Parallel(n_jobs=multiprocessing.cpu_count(), backend="threading") \
        #     (delayed(self.mrm)(relation_dict, relation_dict_reversed, v_star, seed_pair=seed_pair, k=40)
        #      for seed_pair in tqdm_progress)

        results = []
        for seed_pair in tqdm_progress:
            results.append(self.mrm(relation_dict, v_star, seed_pair=seed_pair, k=40))
            tqdm_progress.set_description(
                f'Medical Relatedness {self.relation} Choi ({self.dataset}|{self.algorithm}|{self.preprocessing}): '
                f'{sum(results) / len(results):.5f} mean, '
                f'{max(results):.5f} max')
            tqdm_progress.update()

        if len(results) == 0:
            return 0, 0
        return sum(results) / len(results), max(results)


class MedicalRelatednessMayTreatChoi(MedicalRelatednessChoi):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator]):
        super().__init__(embedding=embedding,
                         umls_mapper=umls_mapper,
                         relation=Relation.MAY_TREAT,
                         evaluators=evaluators)


class MedicalRelatednessMayPreventChoi(MedicalRelatednessChoi):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator]):
        super().__init__(embedding=embedding,
                         umls_mapper=umls_mapper,
                         relation=Relation.MAY_PREVENT,
                         evaluators=evaluators)


class HumanAssessmentTypes(Enum):
    # RELATEDNESS = "relatedness"
    RELATEDNESS_CONT = "relatedness_cont"
    SIMILARITY_CONT = "similarity_cont"
    MAYOSRS = "MayoSRS"


class HumanAssessment(Benchmark):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator],
                 use_spearman: bool = True,
                 asessment_type: HumanAssessmentTypes = None):
        super().__init__(embedding=embedding, umls_mapper=umls_mapper)
        self.srs_evaluator = None
        self.umls_evaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator
            if isinstance(evaluator, SRSEvaluator):
                self.srs_evaluator = evaluator
        self.asessment_type = asessment_type
        self.use_spearman = use_spearman

    def get_mae(self, human_assessment_dict) -> Tuple[float, float]:
        sigma = []
        tqdm_bar = tqdm(human_assessment_dict.items())
        total_count = 0
        found_count = 0
        for concept, other_concepts in tqdm_bar:
            concept_vec = self.get_concept_vector(concept)
            if concept_vec is not None:
                for other_concept in other_concepts:
                    total_count += 1
                    other_concept_vec = self.get_concept_vector(other_concept)
                    if other_concept_vec is not None:
                        distance = abs(human_assessment_dict[concept][other_concept]
                                       - self.cosine(vector1=concept_vec, vector2=other_concept_vec,
                                                     same_vec_zero=not(concept == other_concept)))
                        sigma.append(distance)
                        tqdm_bar.set_description(f"{self.__class__.__name__}  ({self.dataset}|{self.algorithm}|"
                                                 f"{self.preprocessing}): "
                                                 f"{sum(sigma) / len(sigma):.4f}")
                        found_count += 1
                        tqdm_bar.update()
            else:
                total_count += 1

        # print(f'found {len(sigma)} assessments in embeddings')
        benchmark_coverage = found_count / total_count
        return sum(sigma) / len(sigma), benchmark_coverage

    def get_spearman(self, human_assessment_dict) -> Tuple[float, float]:
        human_assessment_values = []
        cosine_values = []
        total_count = 0
        found_count = 0
        found_concepts = []
        all_concepts = []
        tqdm_bar = tqdm(human_assessment_dict.items(), total=len(human_assessment_dict))
        # suma = 0
        for concept, other_concepts in tqdm_bar:
            total_count += len(other_concepts)
            for c in other_concepts:
                all_concepts.append((concept, c))
            concept_vec = self.get_concept_vector(concept, give_none=True)
            if concept_vec is not None:
                for other_concept in other_concepts:
                    other_concept_vec = self.get_concept_vector(other_concept, give_none=True)
                    if other_concept_vec is not None:
                        # cos = self.cosine(vector1=concept_vec, vector2=other_concept_vec,
                        #                   same_vec_zero=not(concept == other_concept))
                        cos = self.cosine(vector1=concept_vec, vector2=other_concept_vec,
                                          same_vec_zero=False)
                        if cos == 1 and concept != other_concept:
                            pass
                            # human_assessment_values.append(0)
                            # cosine_values.append(cos)
                        else:
                            human_assessment_values.append(human_assessment_dict[concept][other_concept])
                            cosine_values.append(cos)
                            found_count += 1
                            found_concepts.append((concept, other_concept))
                        tqdm_bar.set_description(f"{self.__class__.__name__} Beam ({self.dataset}|{self.algorithm}|{self.preprocessing})")
                        tqdm_bar.update()

        if len(human_assessment_values) > 0 and len(cosine_values) > 0:
            cor, _ = spearmanr(human_assessment_values, cosine_values)
        else:
            cor = 0
        benchmark_coverage = found_count / total_count
        # print(suma)
        # print('cov1:', benchmark_coverage)
        # print('cov2:', len(found_concepts)/len(all_concepts))
        # print(len(found_concepts), len(all_concepts))
        # print('found:', found_concepts)
        # print('total', all_concepts)
        return cor, benchmark_coverage

    def human_assessments(self, human_assestment_type: HumanAssessmentTypes) -> Tuple[float, float]:
        if not self.use_spearman:
            if human_assestment_type == HumanAssessmentTypes.RELATEDNESS_CONT:
                return self.get_mae(self.srs_evaluator.human_relatedness_cont)
            elif human_assestment_type == HumanAssessmentTypes.SIMILARITY_CONT:
                return self.get_mae(self.srs_evaluator.human_similarity_cont)
            else:
                return self.get_mae(self.srs_evaluator.human_relatedness_mayo_srs)
        else:
            if human_assestment_type == HumanAssessmentTypes.RELATEDNESS_CONT:
                return self.get_spearman(self.srs_evaluator.human_relatedness_cont)
            elif human_assestment_type == HumanAssessmentTypes.SIMILARITY_CONT:
                return self.get_spearman(self.srs_evaluator.human_similarity_cont)
            else:
                return self.get_spearman(self.srs_evaluator.human_relatedness_mayo_srs)

    def evaluate(self) -> Tuple[float, float]:
        return self.human_assessments(self.asessment_type)


class HumanAssessmentSimilarityCont(HumanAssessment):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator],
                 use_spearman: bool = True):
        super().__init__(embedding=embedding,
                         umls_mapper=umls_mapper,
                         evaluators=evaluators,
                         use_spearman=use_spearman,
                         asessment_type=HumanAssessmentTypes.SIMILARITY_CONT)
        self.umls_evaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator


class HumanAssessmentRelatednessCont(HumanAssessment):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator],
                 use_spearman: bool = True):
        super().__init__(embedding=embedding,
                         umls_mapper=umls_mapper,
                         evaluators=evaluators,
                         use_spearman=use_spearman,
                         asessment_type=HumanAssessmentTypes.RELATEDNESS_CONT)
        self.umls_evaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator


# class HumanAssessmentRelatedness(HumanAssessment):
#     def __init__(self, embedding: Embedding,
#                  umls_mapper: UMLSMapper,
#                  evaluators: List[Evaluator],
#                  use_spearman: bool = True):
#         super().__init__(embedding=embedding,
#                          umls_mapper=umls_mapper,
#                          evaluators=evaluators,
#                          use_spearman=use_spearman,
#                          asessment_type=HumanAssessmentTypes.RELATEDNESS)
#         self.umls_evaluator = None
#         for evaluator in evaluators:
#             if isinstance(evaluator, UMLSEvaluator):
#                 self.umls_evaluator = evaluator


class HumanAssessmentMayoSRS(HumanAssessment):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator],
                 use_spearman: bool = True):
        super().__init__(embedding=embedding,
                         umls_mapper=umls_mapper,
                         evaluators=evaluators,
                         use_spearman=use_spearman,
                         asessment_type=HumanAssessmentTypes.MAYOSRS)
        self.umls_evaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator


class AbstractBeamBenchmark(Benchmark, ABC):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper):
        super().__init__(embedding=embedding, umls_mapper=umls_mapper)

    @staticmethod
    def sample(elements: List, bootstraps: int = 10):
        if len(elements) < bootstraps:
            return elements
        random.seed(42)
        return random.sample(elements, bootstraps)

    def bootstrap(self, category_concepts: List[str], other_concepts: List[str], sample_size: int = 10000):

        concept_sample = self.sample(category_concepts, sample_size)
        other_sample = self.sample(other_concepts, sample_size)

        bootstrap_values = [self.cosine(vector1=self.get_concept_vector(concept),
                                        vector2=self.get_concept_vector(other_concept),
                                        same_vec_zero=not(concept == other_concept))
                            for concept, other_concept in zip(concept_sample, other_sample)]

        threshold = np.quantile(bootstrap_values, 1 - constant.SIG_LEVEL)

        return threshold

    @abstractmethod
    def calculate_power(self):
        pass

    def evaluate(self) -> float:
        return self.calculate_power()


class SemanticTypeBeam(AbstractBeamBenchmark):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator]):
        super().__init__(embedding=embedding, umls_mapper=umls_mapper)
        self.umls_evaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator

    def calculate_power(self):
        total_positives = 0
        total_observed_scores = 0
        total_observed_scores_strict = 0
        # categories = self.umls_evaluator.category2concepts.keys()
        categories = ['Pharmacologic Substance',
                      'Disease or Syndrome',
                      'Neoplastic Process',
                      'Clinical Drug',
                      'Finding',
                      'Injury or Poisoning',
                      ]

        all_concepts = set([concept for concept in self.umls_evaluator.concept2category.keys()
                            if concept in self.vocab])
        tqdm_bar = tqdm(categories, total=len(categories))
        for category in tqdm_bar:
            same_type_concepts = [concept for concept in self.umls_evaluator.category2concepts[category]
                                  if concept in self.vocab]
            total_observed_scores_strict += len(self.umls_evaluator.category2concepts[category])-len(same_type_concepts)
            other_type_concepts = list(all_concepts.difference(same_type_concepts))

            if len(same_type_concepts) == 0 or len(other_type_concepts) == 0:
                continue

            sig_threshold = self.bootstrap(same_type_concepts, other_type_concepts, sample_size=10000)

            num_observed_scores = 0
            num_positives = 0
            sampled_same_type_concepts = self.sample(same_type_concepts, 2000)
            for i, first_category_concept in enumerate(sampled_same_type_concepts):
                for j, second_category_concept in enumerate(sampled_same_type_concepts):
                    if j <= i:
                        continue
                    observed_score = self.cosine(vector1=self.get_concept_vector(first_category_concept),
                                                 vector2=self.get_concept_vector(second_category_concept),
                                                 same_vec_zero=not(first_category_concept == second_category_concept)
                                                 )

                    if observed_score >= sig_threshold:
                        num_positives += 1
                    num_observed_scores += 1

            total_positives += num_positives
            total_observed_scores += num_observed_scores
            total_observed_scores_strict += num_observed_scores
            tqdm_bar.set_description(f"Semantic Type Beam ({self.dataset}|{self.algorithm}|{self.preprocessing}): "
                                     f"{sig_threshold:.4f} threshold, "
                                     f"{(total_positives / total_observed_scores):.4f} score")
            tqdm_bar.update()

        r_1 = 0
        if total_observed_scores != 0:
            r_1 = total_positives / total_observed_scores
        r_2 = 0
        if total_observed_scores_strict != 0:
            r_2 = total_positives / total_observed_scores_strict
        return r_1, r_2


class NDFRTBeam(AbstractBeamBenchmark):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator]):
        super().__init__(embedding=embedding, umls_mapper=umls_mapper)
        self.umls_evaluator = None
        self.ndf_evaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator
            if isinstance(evaluator, NDFEvaluator):
                self.ndf_evaluator = evaluator

    def get_concepts_of_semantic_types(self, semantic_types):
        concepts = set()
        for semantic_type in semantic_types:
            concepts.update([concept
                             for concept in self.umls_evaluator.category2concepts[semantic_type]
                             if concept in self.vocab])
        return list(concepts)

    def calculate_power(self):
        total_positives = 0
        total_observed_scores = 0
        total_observed_scores_strict = 0
        treatment_conditions = []
        for treatment, conditions in self.ndf_evaluator.may_prevent.items():
            for condition in conditions:
                if treatment in self.vocab and condition in self.vocab:
                    treatment_conditions.append((treatment, condition))
                else:
                    total_observed_scores_strict += 1

        for treatment, conditions in self.ndf_evaluator.may_treat.items():
            for condition in conditions:
                if treatment in self.vocab and condition in self.vocab:
                    treatment_conditions.append((treatment, condition))
                else:
                    total_observed_scores_strict += 1

        tqdm_bar = tqdm(treatment_conditions, total=len(treatment_conditions))
        for treatment_condition in tqdm_bar:
            current_treatment, current_condition = treatment_condition
            if current_treatment in self.umls_evaluator.concept2category.keys() \
                    and current_condition in self.umls_evaluator.concept2category.keys():
                treatment_semantic_types = self.umls_evaluator.concept2category[current_treatment]
                condition_semantic_types = self.umls_evaluator.concept2category[current_condition]
            else:
                continue

            treatment_concepts = self.get_concepts_of_semantic_types(treatment_semantic_types)
            condition_concepts = self.get_concepts_of_semantic_types(condition_semantic_types)

            if len(treatment_concepts) == 0 or len(condition_concepts) == 0:
                continue

            sig_threshold = self.bootstrap(treatment_concepts, condition_concepts, sample_size=10000)

            num_observed_scores = 0
            num_positives = 0

            observed_score = self.cosine(vector1=self.get_concept_vector(current_treatment),
                                         vector2=self.get_concept_vector(current_condition),
                                         same_vec_zero=not(current_treatment == current_condition)
                                         )
            if observed_score >= sig_threshold:
                num_positives += 1
            num_observed_scores += 1

            total_positives += num_positives
            total_observed_scores += num_observed_scores
            total_observed_scores_strict += num_observed_scores
            tqdm_bar.set_description(f"NDFRT Beam ({self.dataset}|{self.algorithm}|{self.preprocessing}): "
                                     f"{sig_threshold:.4f} threshold, "
                                     f"{(total_positives / total_observed_scores):.4f} score")
            tqdm_bar.update()

        r_1 = 0
        if total_observed_scores != 0:
            r_1 = total_positives / total_observed_scores
        r_2 = 0
        if total_observed_scores_strict != 0:
            r_2 = total_positives / total_observed_scores_strict
        return r_1, r_2


class CausalityBeam(AbstractBeamBenchmark):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator]):
        super().__init__(embedding=embedding, umls_mapper=umls_mapper)
        self.umls_evaluator = None
        self.mrrelevaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator
            if isinstance(evaluator, MRRELEvaluator):
                self.mrrelevaluator = evaluator

    def get_concepts_of_semantic_types(self, semantic_types):
        concepts = set()
        for semantic_type in semantic_types:
            concepts.update([concept
                             for concept in self.umls_evaluator.category2concepts[semantic_type]
                             if concept in self.vocab])
        return list(concepts)

    def calculate_power(self):
        total_positives = 0
        total_observed_scores = 0
        total_observed_scores_strict = 0
        causative_relations = []
        for cause, effects in self.mrrelevaluator.mrrel_cause.items():
            for effect in effects:
                if cause in self.vocab and effect in self.vocab:
                    causative_relations.append((cause, effect))
                else:
                    total_observed_scores_strict += 1

        tqdm_bar = tqdm(causative_relations, total=len(causative_relations))
        for treatment_condition in tqdm_bar:
            current_cause, current_effect = treatment_condition
            if current_cause in self.umls_evaluator.concept2category.keys() \
                    and current_effect in self.umls_evaluator.concept2category.keys():
                cause_semantic_types = self.umls_evaluator.concept2category[current_cause]
                effect_semantic_types = self.umls_evaluator.concept2category[current_effect]
            else:
                continue

            cause_concepts = self.get_concepts_of_semantic_types(cause_semantic_types)
            effect_concepts = self.get_concepts_of_semantic_types(effect_semantic_types)

            if len(cause_concepts) == 0 or len(effect_concepts) == 0:
                continue

            sig_threshold = self.bootstrap(cause_concepts, effect_concepts, sample_size=10000)

            num_observed_scores = 0
            num_positives = 0

            observed_score = self.cosine(vector1=self.get_concept_vector(current_cause),
                                         vector2=self.get_concept_vector(current_effect),
                                         same_vec_zero=not(current_cause == current_effect)
                                         )
            if observed_score >= sig_threshold:
                num_positives += 1
            num_observed_scores += 1

            total_positives += num_positives
            total_observed_scores += num_observed_scores
            total_observed_scores_strict += num_observed_scores
            tqdm_bar.set_description(f"Causality Beam ({self.dataset}|{self.algorithm}|{self.preprocessing}): "
                                     f"{sig_threshold:.4f} threshold, "
                                     f"{(total_positives / total_observed_scores):.4f} score")
            tqdm_bar.update()

        r_1 = 0
        if total_observed_scores != 0:
            r_1 = total_positives / total_observed_scores
        r_2 = 0
        if total_observed_scores_strict != 0:
            r_2 = total_positives / total_observed_scores_strict
        return r_1, r_2


class AssociationBeam(AbstractBeamBenchmark):
    def __init__(self, embedding: Embedding,
                 umls_mapper: UMLSMapper,
                 evaluators: List[Evaluator]):
        super().__init__(embedding=embedding, umls_mapper=umls_mapper)
        self.umls_evaluator = None
        self.mrrelevaluator = None
        for evaluator in evaluators:
            if isinstance(evaluator, UMLSEvaluator):
                self.umls_evaluator = evaluator
            if isinstance(evaluator, MRRELEvaluator):
                self.mrrelevaluator = evaluator

    def get_concepts_of_semantic_types(self, semantic_types):
        concepts = set()
        for semantic_type in semantic_types:
            concepts.update([concept
                             for concept in self.umls_evaluator.category2concepts[semantic_type]
                             if concept in self.vocab])
        return list(concepts)

    def calculate_power(self):
        total_positives = 0
        total_observed_scores = 0
        total_observed_scores_strict = 0
        associated_relations = []
        for concept, associated_concepts in self.mrrelevaluator.mrrel_association.items():
            for associated_concept in associated_concepts:
                if concept in self.vocab and associated_concept in self.vocab:
                    associated_relations.append((concept, associated_concept))
                else:
                    total_observed_scores_strict += 1

        tqdm_bar = tqdm(associated_relations, total=len(associated_relations))
        for treatment_condition in tqdm_bar:
            current_concept, current_association = treatment_condition
            if current_concept in self.umls_evaluator.concept2category.keys() \
                    and current_association in self.umls_evaluator.concept2category.keys():
                concept_semantic_types = self.umls_evaluator.concept2category[current_concept]
                associated_semantic_types = self.umls_evaluator.concept2category[current_association]
            else:
                continue

            related_concepts = self.get_concepts_of_semantic_types(concept_semantic_types)
            associated_concepts = self.get_concepts_of_semantic_types(associated_semantic_types)

            if len(related_concepts) == 0 or len(associated_concepts) == 0:
                continue

            sig_threshold = self.bootstrap(related_concepts, associated_concepts, sample_size=10000)

            num_observed_scores = 0
            num_positives = 0

            observed_score = self.cosine(vector1=self.get_concept_vector(current_concept),
                                         vector2=self.get_concept_vector(current_association),
                                         same_vec_zero=not(current_concept == current_association)
                                         )
            if observed_score >= sig_threshold:
                num_positives += 1
            num_observed_scores += 1

            total_positives += num_positives
            total_observed_scores += num_observed_scores
            total_observed_scores_strict += num_observed_scores
            tqdm_bar.set_description(f"Association Beam ({self.dataset}|{self.algorithm}|{self.preprocessing}): "
                                     f"{sig_threshold:.4f} threshold, "
                                     f"{(total_positives / total_observed_scores):.4f} score")
            tqdm_bar.update()

        r_1 = 0
        if total_observed_scores != 0:
            r_1 = total_positives / total_observed_scores
        r_2 = 0
        if total_observed_scores_strict != 0:
            r_2 = total_positives / total_observed_scores_strict
        return r_1, r_2
