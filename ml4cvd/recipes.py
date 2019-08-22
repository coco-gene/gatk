# recipes.py

# Imports
import os
import csv
import logging
import numpy as np
from functools import reduce
from timeit import default_timer as timer
from collections import Counter, defaultdict

from ml4cvd.defines import TENSOR_EXT
from ml4cvd.arguments import parse_args
from ml4cvd.tensor_map_maker import write_tensor_maps
from ml4cvd.tensor_writer_ukbb import write_tensors, append_float_csv, append_gene_csv
from ml4cvd.tensor_generators import TensorGenerator, test_train_valid_tensor_generators, big_batch_from_minibatch_generator
from ml4cvd.metrics import get_roc_aucs, get_precision_recall_aucs, get_pearson_coefficients, log_aucs, log_pearson_coefficients
from ml4cvd.explorations import sample_from_char_model, mri_dates, ecg_dates, predictions_to_pngs, sort_csv, plot_heatmap_from_tensor_files
from ml4cvd.explorations import plot_histograms_from_tensor_files_in_pdf, plot_while_learning, find_tensors, tabulate_correlations_from_tensor_files, test_labels_to_label_dictionary
from ml4cvd.models import make_multimodal_to_multilabel_model, train_model_from_generators, get_model_inputs_outputs, make_shallow_model, \
    make_character_model_plus, embed_model_predict, make_translation_model
from ml4cvd.plots import evaluate_predictions, plot_scatters, plot_rocs, plot_precision_recalls, subplot_rocs, subplot_comparison_rocs, subplot_scatters, subplot_comparison_scatters, plot_tsne


def run(args):
    try:
        # Keep track of elapsed execution time
        start_time = timer()

        if 'tensorize' == args.mode:
            write_tensors(args.id, args.xml_folder, args.zip_folder, args.output_folder, args.tensors, args.dicoms, args.volume_csv, args.lv_mass_csv,
                          args.mri_field_ids, args.xml_field_ids, args.x, args.y, args.z, args.zoom_x, args.zoom_y, args.zoom_width, args.zoom_height,
                          args.write_pngs, args.min_sample_id, args.max_sample_id, args.min_values)
        elif 'train' == args.mode:
            train_multimodal_multitask(args)
        elif 'test' == args.mode:
            test_multimodal_multitask(args)
        elif 'compare' == args.mode:
            compare_multimodal_multitask_models(args)
        elif 'infer' == args.mode:
            infer_multimodal_multitask(args)
        elif 'translate' == args.mode:
            train_translation_model(args)
        elif 'test_scalar' == args.mode:
            test_multimodal_scalar_tasks(args)
        elif 'compare_scalar' == args.mode:
            compare_multimodal_scalar_task_models(args)
        elif 'segmentation_to_pngs' == args.mode:
            segmentation_to_pngs(args)
        elif 'plot_while_training' == args.mode:
            plot_while_training(args)
        elif 'plot_mri_dates' == args.mode:
            mri_dates(args.tensors, args.output_folder, args.id)
        elif 'plot_ecg_dates' == args.mode:
            ecg_dates(args.tensors, args.output_folder, args.id)
        elif 'plot_histograms' == args.mode:
            plot_histograms_from_tensor_files_in_pdf(args.id, args.tensors, args.output_folder, args.max_samples)
        elif 'plot_heatmap' == args.mode:
            plot_heatmap_from_tensor_files(args.id, args.tensors, args.output_folder, args.min_samples, args.max_samples)
        elif 'tabulate_correlations' == args.mode:
            tabulate_correlations_from_tensor_files(args.id, args.tensors, args.output_folder, args.min_samples, args.max_samples)
        elif 'train_shallow' == args.mode:
            train_shallow_model(args)
        elif 'train_char' == args.mode:
            train_char_model(args)
        elif 'write_tensor_maps' == args.mode:
            write_tensor_maps(args)
        elif 'find_tensors' == args.mode:
            find_tensors(os.path.join(args.output_folder, args.id, 'found_'+args.id+'.txt'), args.tensors, args.tensor_maps_out)
        elif 'sort_csv' == args.mode:
            sort_csv(args.app_csv, args.volume_csv)
        elif 'append_float_csv' == args.mode:
            append_float_csv(args.tensors, args.app_csv, 'continuous', '\t')
        elif 'append_gene_csv' == args.mode:
            append_gene_csv(args.tensors, args.app_csv, ',')
        else:
            raise ValueError('Unknown mode:', args.mode)

    except Exception as e:
        logging.exception(e)

    end_time = timer()
    elapsed_time = end_time - start_time
    logging.info("Executed the '{}' operation in {:.2f} seconds".format(args.mode, elapsed_time))


def train_multimodal_multitask(args):
    generate_train, generate_valid, generate_test = test_train_valid_tensor_generators(args.tensor_maps_in, args.tensor_maps_out, args.tensors,
                                                                                       args.batch_size, args.valid_ratio, args.test_ratio,
                                                                                       args.test_modulo, args.balance_csvs)

    model = make_multimodal_to_multilabel_model(args.model_file, args.model_layers, args.model_freeze, args.tensor_maps_in, args.tensor_maps_out,
                                                args.activation, args.dense_layers, args.dropout, args.mlp_concat, args.conv_layers, args.max_pools,
                                                args.res_layers, args.dense_blocks, args.block_size, args.conv_bn, args.conv_x, args.conv_y,
                                                args.conv_z, args.conv_dropout, args.conv_width, args.u_connect, args.pool_x, args.pool_y,
                                                args.pool_z, args.padding, args.learning_rate)

    model = train_model_from_generators(model, generate_train, generate_valid, args.training_steps, args.validation_steps, args.batch_size,
                                        args.epochs, args.patience, args.output_folder, args.id, args.inspect_model, args.inspect_show_labels)

    out_path = os.path.join(args.output_folder, args.id + '/')
    test_data, test_labels, test_paths = big_batch_from_minibatch_generator(args.tensor_maps_in, args.tensor_maps_out, generate_test, args.test_steps)
    return _predict_and_evaluate(model, test_data, test_labels, args.tensor_maps_in, args.tensor_maps_out, args.batch_size, args.hidden_layer, out_path, test_paths, args.alpha)


def test_multimodal_multitask(args):
    _, _, generate_test = test_train_valid_tensor_generators(args.tensor_maps_in, args.tensor_maps_out, args.tensors, args.batch_size,
                                                             args.valid_ratio, args.test_ratio, args.test_modulo, args.balance_csvs)

    model = make_multimodal_to_multilabel_model(args.model_file, args.model_layers, args.model_freeze, args.tensor_maps_in, args.tensor_maps_out,
                                                args.activation, args.dense_layers, args.dropout, args.mlp_concat, args.conv_layers, args.max_pools,
                                                args.res_layers, args.dense_blocks, args.block_size, args.conv_bn, args.conv_x, args.conv_y,
                                                args.conv_z, args.conv_dropout, args.conv_width, args.u_connect, args.pool_x, args.pool_y,
                                                args.pool_z, args.padding, args.learning_rate)

    out_path = os.path.join(args.output_folder, args.id + '/')
    data, labels, paths = big_batch_from_minibatch_generator(args.tensor_maps_in, args.tensor_maps_out, generate_test, args.test_steps)
    return _predict_and_evaluate(model, data, labels, args.tensor_maps_in, args.tensor_maps_out, args.batch_size, args.hidden_layer, out_path, paths, args.alpha)
  

def test_multimodal_scalar_tasks(args):
    _, _, generate_test = test_train_valid_tensor_generators(args.tensor_maps_in, args.tensor_maps_out, args.tensors, args.batch_size,
                                                             args.valid_ratio, args.test_ratio, args.test_modulo, args.balance_csvs)

    model = make_multimodal_to_multilabel_model(args.model_file, args.model_layers, args.model_freeze, args.tensor_maps_in, args.tensor_maps_out,
                                                args.activation, args.dense_layers, args.dropout, args.mlp_concat, args.conv_layers, args.max_pools,
                                                args.res_layers, args.dense_blocks, args.block_size, args.conv_bn, args.conv_x, args.conv_y,
                                                args.conv_z, args.conv_dropout, args.conv_width, args.u_connect, args.pool_x, args.pool_y,
                                                args.pool_z, args.padding, args.learning_rate)

    p = os.path.join(args.output_folder, args.id + '/')
    return _predict_scalars_and_evaluate_from_generator(model, generate_test, args.tensor_maps_out, args.test_steps, args.hidden_layer, p, args.alpha)


def compare_multimodal_multitask_models(args):
    _, _, generate_test = test_train_valid_tensor_generators(args.tensor_maps_in, args.tensor_maps_out, args.tensors, args.batch_size,
                                                             args.valid_ratio, args.test_ratio, args.test_modulo, args.balance_csvs)
    models_inputs_outputs = get_model_inputs_outputs(args.model_files, args.tensor_maps_in, args.tensor_maps_out)
    input_data, output_data, paths = big_batch_from_minibatch_generator(args.tensor_maps_in, args.tensor_maps_out, generate_test, args.test_steps)
    common_outputs = _get_common_outputs(models_inputs_outputs, 'output')
    predictions = _get_predictions(args, models_inputs_outputs, input_data, common_outputs, 'input', 'output')
    _calculate_and_plot_prediction_stats(args, predictions, output_data, paths)


def compare_multimodal_scalar_task_models(args):
    _, _, generate_test = test_train_valid_tensor_generators(args.tensor_maps_in, args.tensor_maps_out, args.tensors, args.batch_size,
                                                             args.valid_ratio, args.test_ratio, args.test_modulo, args.balance_csvs)
    models_io = get_model_inputs_outputs(args.model_files, args.tensor_maps_in, args.tensor_maps_out)
    outs = _get_common_outputs(models_io, "output")
    predictions, labels, paths = _scalar_predictions_from_generator(args, models_io, generate_test, args.test_steps, outs, "input", "output")
    _calculate_and_plot_prediction_stats(args, predictions, labels, paths)


def train_translation_model(args):
    generate_train, generate_valid, generate_test = test_train_valid_tensor_generators(args.tensor_maps_in, args.tensor_maps_out, args.tensors,
                                                                                       args.batch_size, args.valid_ratio, args.test_ratio,
                                                                                       args.test_modulo, args.balance_csvs)

    model = make_translation_model(args.model_file, args.model_layers, args.model_freeze, args.tensor_maps_in, args.tensor_maps_out, args.activation,
                                   args.dense_layers, args.dropout, args.mlp_concat, args.conv_layers, args.max_pools, args.res_layers, args.dense_blocks,
                                   args.block_size, args.conv_bn, args.conv_x, args.conv_y, args.conv_z, args.conv_dropout, args.conv_width, args.u_connect,
                                   args.pool_x, args.pool_y, args.pool_z, args.padding, args.learning_rate)

    model = train_model_from_generators(model, generate_train, generate_valid, args.training_steps, args.validation_steps, args.batch_size,
                                        args.epochs, args.patience, args.output_folder, args.id, args.inspect_model, args.inspect_show_labels)

    folder = os.path.join(args.output_folder, args.id + '/')
    test_data, test_labels, test_paths = big_batch_from_minibatch_generator(args.tensor_maps_in, args.tensor_maps_out, generate_test, args.test_steps)
    predictions = model.predict(test_data, batch_size=args.batch_size)
    predictions_to_pngs(predictions, args.tensor_maps_in, args.tensor_maps_out, test_data, test_labels, test_paths, folder)
    return _predict_and_evaluate(model, test_data, test_labels, args.tensor_maps_in, args.tensor_maps_out, args.batch_size, args.hidden_layer, folder, test_paths, args.alpha)


def infer_multimodal_multitask(args):
    stats = Counter()
    tensor_paths_inferred = {}
    inference_tsv = os.path.join(args.output_folder, args.id, 'inference_' + args.id + '.tsv')
    tensor_paths = [args.tensors + tp for tp in sorted(os.listdir(args.tensors)) if os.path.splitext(tp)[-1].lower() == TENSOR_EXT]
    # hard code batch size to 1 so we can iterate over file names and generated tensors together in the tensor_paths for loop
    generate_test = TensorGenerator(1, args.tensor_maps_in, args.tensor_maps_out, tensor_paths, keep_paths=True)
    model = make_multimodal_to_multilabel_model(args.model_file, args.model_layers, args.model_freeze, args.tensor_maps_in, args.tensor_maps_out,
                                                args.activation, args.dense_layers, args.dropout, args.mlp_concat, args.conv_layers, args.max_pools,
                                                args.res_layers, args.dense_blocks, args.block_size, args.conv_bn, args.conv_x, args.conv_y,
                                                args.conv_z, args.conv_dropout, args.conv_width, args.u_connect, args.pool_x, args.pool_y,
                                                args.pool_z, args.padding, args.learning_rate)
    
    with open(inference_tsv, mode='w') as inference_file:
        inference_writer = csv.writer(inference_file, delimiter='\t', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        header = ['sample_id']
        for ot, otm in zip(args.output_tensors, args.tensor_maps_out):
            if len(otm.shape) == 1:
                header.extend([ot+'_prediction', ot+'_actual'])
        inference_writer.writerow(header)

        while True:
            input_data, true_label, tensor_path = next(generate_test)
            if tensor_path[0] in tensor_paths_inferred:
                logging.info(f"Inference on {stats['count']} tensors finished. Inference TSV file at: {inference_tsv}")
                break

            prediction = model.predict(input_data)
            if len(args.tensor_maps_out) == 1:
                prediction = [prediction]

            csv_row = [os.path.basename(tensor_path[0]).replace(TENSOR_EXT, '')]  # extract sample id
            for y, tm in zip(prediction, args.tensor_maps_out):
                if len(tm.shape) == 1:
                    csv_row.append(str(tm.rescale(y)[0][0]))  # first index into batch then index into the 1x1 structure
                    if tm.sentinel is not None and tm.sentinel == true_label[tm.output_name()][0][0]:
                        csv_row.append("NA")
                    elif abs(tm.rescale(true_label[tm.output_name()][0][0])) < 0.01:  # LV MASSS HACK
                        csv_row.append("NA")
                    else:
                        csv_row.append(str(tm.rescale(true_label[tm.output_name()])[0][0]))
            inference_writer.writerow(csv_row)

            tensor_paths_inferred[tensor_path[0]] = True
            stats['count'] += 1
            if stats['count'] % 500 == 0:
                logging.info(f"Wrote:{stats['count']} rows of inference.  Last tensor:{tensor_path[0]}")


def train_shallow_model(args):
    generate_train, generate_valid, generate_test = test_train_valid_tensor_generators(args.tensor_maps_in, args.tensor_maps_out, args.tensors,
                                                                                       args.batch_size, args.valid_ratio, args.test_ratio,
                                                                                       args.test_modulo, args.balance_csvs)

    model = make_shallow_model(args.tensor_maps_in, args.tensor_maps_out, args.learning_rate, args.model_file, args.model_layers)
    model = train_model_from_generators(model, generate_train, generate_valid, args.training_steps, args.validation_steps, args.batch_size,
                                        args.epochs, args.patience, args.output_folder, args.id, args.inspect_model, args.inspect_show_labels)

    p = os.path.join(args.output_folder, args.id + '/')
    test_data, test_labels, test_paths = big_batch_from_minibatch_generator(args.tensor_maps_in, args.tensor_maps_out, generate_test, args.test_steps)
    return _predict_and_evaluate(model, test_data, test_labels, args.tensor_maps_in, args.tensor_maps_out, args.batch_size, args.hidden_layer, p, test_paths, args.alpha)


def train_char_model(args):
    base_model = make_multimodal_to_multilabel_model(args.model_file, args.model_layers, args.model_freeze, args.tensor_maps_in, args.tensor_maps_out,
                                                     args.activation, args.dense_layers, args.dropout, args.mlp_concat, args.conv_layers,
                                                     args.max_pools, args.res_layers, args.dense_blocks, args.block_size, args.conv_bn, args.conv_x,
                                                     args.conv_y, args.conv_z, args.conv_dropout, args.conv_width, args.u_connect, args.pool_x,
                                                     args.pool_y, args.pool_z, args.padding, args.learning_rate)

    model, char_model = make_character_model_plus(args.tensor_maps_in, args.tensor_maps_out, args.learning_rate, base_model, args.model_layers)
    generate_train, generate_valid, generate_test = test_train_valid_tensor_generators(args.tensor_maps_in, args.tensor_maps_out, args.tensors,
                                                                                       args.batch_size, args.valid_ratio, args.test_ratio,
                                                                                       args.test_modulo, args.balance_csvs)

    model = train_model_from_generators(model, generate_train, generate_valid, args.training_steps, args.validation_steps, args.batch_size,
                                        args.epochs, args.patience, args.output_folder, args.id, args.inspect_model, args.inspect_show_labels)
    test_batch, _, test_paths = next(generate_test)
    sample_from_char_model(char_model, test_batch, test_paths)

    output_path = os.path.join(args.output_folder, args.id + '/')
    data, labels, paths = big_batch_from_minibatch_generator(args.tensor_maps_in, args.tensor_maps_out, generate_test, args.test_steps)
    return _predict_and_evaluate(model, data, labels, args.tensor_maps_in, args.tensor_maps_out, args.batch_size, args.hidden_layer, output_path, paths, args.alpha)


def segmentation_to_pngs(args):
    _, _, generate_test = test_train_valid_tensor_generators(args.tensor_maps_in, args.tensor_maps_out, args.tensors, args.batch_size*args.test_steps,
                                                             args.valid_ratio, args.test_ratio, args.test_modulo, args.balance_csvs)

    model = make_multimodal_to_multilabel_model(args.model_file, args.model_layers, args.model_freeze, args.tensor_maps_in, args.tensor_maps_out,
                                                args.activation, args.dense_layers, args.dropout, args.mlp_concat, args.conv_layers, args.max_pools,
                                                args.res_layers, args.dense_blocks, args.block_size, args.conv_bn, args.conv_x, args.conv_y,
                                                args.conv_z, args.conv_dropout, args.conv_width, args.u_connect, args.pool_x, args.pool_y,
                                                args.pool_z, args.padding, args.learning_rate)

    data, labels, paths = big_batch_from_minibatch_generator(args.tensor_maps_in, args.tensor_maps_out, generate_test, args.test_steps)
    predictions = model.predict(data, batch_size=args.batch_size)
    if len(args.tensor_maps_out) == 1:
        predictions = [predictions]
    folder = os.path.join(args.output_folder, args.id) + '/'
    predictions_to_pngs(predictions, args.tensor_maps_in, args.tensor_maps_out, data, labels, paths, folder)


def plot_while_training(args):
    generate_train, _, generate_test = test_train_valid_tensor_generators(args.tensor_maps_in, args.tensor_maps_out, args.tensors, args.batch_size,
                                                                          args.valid_ratio, args.test_ratio, args.test_modulo, args.balance_csvs)

    test_data, test_labels, test_paths = big_batch_from_minibatch_generator(args.tensor_maps_in, args.tensor_maps_out, generate_test, args.test_steps)
    model = make_multimodal_to_multilabel_model(args.model_file, args.model_layers, args.model_freeze, args.tensor_maps_in, args.tensor_maps_out,
                                                args.activation, args.dense_layers, args.dropout, args.mlp_concat, args.conv_layers, args.max_pools,
                                                args.res_layers, args.dense_blocks, args.block_size, args.conv_bn, args.conv_x, args.conv_y,
                                                args.conv_z, args.conv_dropout, args.conv_width, args.u_connect, args.pool_x, args.pool_y,
                                                args.pool_z, args.padding, args.learning_rate)

    plot_folder = os.path.join(args.output_folder, args.id, 'training_frames/')
    plot_while_learning(model, args.tensor_maps_in, args.tensor_maps_out, generate_train, test_data, test_labels, test_paths, args.epochs,
                        args.batch_size, args.training_steps, plot_folder, args.write_pngs)


def _predict_and_evaluate(model, test_data, test_labels, tensor_maps_in, tensor_maps_out, batch_size, hidden_layer, plot_path, test_paths, alpha):
    layer_names = [layer.name for layer in model.layers]
    performance_metrics = {}
    scatters = []
    rocs = []

    y_predictions = model.predict(test_data, batch_size=batch_size)
    for y, tm in zip(y_predictions, tensor_maps_out):
        if tm.output_name() not in layer_names:
            continue
        if not isinstance(y_predictions, list):  # When models have a single output model.predict returns a ndarray otherwise it returns a list
            y = y_predictions
        y_truth = np.array(test_labels[tm.output_name()])
        performance_metrics.update(evaluate_predictions(tm, y, y_truth, tm.name, plot_path, test_paths, rocs=rocs, scatters=scatters))

    if len(rocs) > 1:
        subplot_rocs(rocs, plot_path)
    if len(scatters) > 1:
        subplot_scatters(scatters, plot_path)

    test_labels_1d = {tm: np.array(test_labels[tm.output_name()]) for tm in tensor_maps_out if tm.output_name() in test_labels}
    _tsne_wrapper(model, hidden_layer, alpha, plot_path, test_paths, test_labels_1d, test_data=test_data, tensor_maps_in=tensor_maps_in, batch_size=batch_size)

    return performance_metrics


def _predict_scalars_and_evaluate_from_generator(model, test_generator, tensor_maps_out, steps, hidden_layer, plot_path, alpha):
    layer_names = [layer.name for layer in model.layers]
    model_predictions = [tm.output_name() for tm in tensor_maps_out if tm.output_name() in layer_names]
    scalar_predictions = {tm.output_name(): [] for tm in tensor_maps_out if len(tm.shape) == 1 and tm.output_name() in layer_names}
    test_labels = {tm.output_name(): [] for tm in tensor_maps_out if len(tm.shape) == 1}

    logging.info(f" in scalar predict {model_predictions} scalar predict names: {scalar_predictions.keys()} test labels: {test_labels.keys()}")
    embeddings = []
    test_paths = []
    for i in range(steps):
        batch_data, batch_labels, batch_paths = next(test_generator)
        y_predictions = model.predict(batch_data)
        test_paths.extend(batch_paths)
        if hidden_layer in layer_names:
            x_embed = embed_model_predict(model, args.tensor_maps_in, hidden_layer, batch_data, 2)
            embeddings.extend(np.copy(np.reshape(x_embed, (x_embed.shape[0], np.prod(x_embed.shape[1:])))))

        for tm_output_name in test_labels:
            test_labels[tm_output_name].extend(np.copy(batch_labels[tm_output_name]))

        for y, tm_output_name in zip(y_predictions, model_predictions):
            if not isinstance(y_predictions, list):  # When models have a single output model.predict returns a ndarray otherwise it returns a list
                y = y_predictions
            if tm_output_name in scalar_predictions:
                scalar_predictions[tm_output_name].extend(np.copy(y))

    performance_metrics = {}
    scatters = []
    rocs = []
    for tm in tensor_maps_out:
        if tm.output_name() in scalar_predictions:
            y_predict = np.array(scalar_predictions[tm.output_name()])
            y_truth = np.array(test_labels[tm.output_name()])
            performance_metrics.update(evaluate_predictions(tm, y_predict, y_truth, tm.name, plot_path, test_paths, rocs=rocs, scatters=scatters))

    if len(rocs) > 1:
        subplot_rocs(rocs, plot_path)
    if len(scatters) > 1:
        subplot_scatters(scatters, plot_path)
    if len(embeddings) > 0:
        test_labels_1d = {tm: np.array(test_labels[tm.output_name()]) for tm in tensor_maps_out if tm.output_name() in test_labels}
        _tsne_wrapper(model, hidden_layer, alpha, plot_path, test_paths, test_labels_1d, embeddings=embeddings)

    return performance_metrics


def _get_common_outputs(models_inputs_outputs, output_prefix):
    """Returns a set of outputs common to all the models so we can compare the models according to those outputs only"""
    all_outputs = []
    for (_, ios) in models_inputs_outputs.items():
        outputs = {k: v for (k, v) in ios.items() if k == output_prefix}
        for (_, output) in outputs.items():
            all_outputs.append(set(output))
    return reduce(set.intersection, all_outputs)


def _get_predictions(args, models_inputs_outputs, input_data, outputs, input_prefix, output_prefix):
    """Makes multi-modal predictions for a given number of models.

    Returns:
        dict: The nested dictionary of predicted values.

            {
                'tensor_map_1':
                    {
                        'model_1': [[value1, value2], [...]],
                        'model_2': [[value3, value4], [...]]
                    },
                'tensor_map_2':
                    {
                        'model_2': [[value5, value6], [...]],
                        'model_3': [[value7, value8], [...]]
                    }
            }
    """
    predictions = defaultdict(dict)
    for model_file in models_inputs_outputs.keys():
        args.model_file = model_file
        args.tensor_maps_in = models_inputs_outputs[model_file][input_prefix]
        args.tensor_maps_out = models_inputs_outputs[model_file][output_prefix]

        model = make_multimodal_to_multilabel_model(args.model_file, args.model_layers, args.model_freeze, args.tensor_maps_in, args.tensor_maps_out,
                                                    args.activation, args.dense_layers, args.dropout, args.mlp_concat, args.conv_layers,
                                                    args.max_pools, args.res_layers, args.dense_blocks, args.block_size, args.conv_bn, args.conv_x,
                                                    args.conv_y, args.conv_z, args.conv_dropout, args.conv_width, args.u_connect, args.pool_x,
                                                    args.pool_y, args.pool_z, args.padding, args.learning_rate)

        model_name = os.path.basename(model_file).replace(TENSOR_EXT, '')

        # We can feed 'model.predict()' the entire input data because it knows what subset to use
        y_pred = model.predict(input_data, batch_size=args.batch_size)

        for i, tm in enumerate(args.tensor_maps_out):
            if tm in outputs:
                if len(args.tensor_maps_out) == 1:
                    predictions[tm][model_name] = y_pred
                else:
                    predictions[tm][model_name] = y_pred[i]

    return predictions


def _scalar_predictions_from_generator(args, models_inputs_outputs, generator, steps, outputs, input_prefix, output_prefix):
    """Makes multi-modal scalar predictions for a given number of models.

    Returns:
        dict: The nested dictionary of predicted values.

            {
                'tensor_map_1':
                    {
                        'model_1': [[value1, value2], [...]],
                        'model_2': [[value3, value4], [...]]
                    },
                'tensor_map_2':
                    {
                        'model_2': [[value5, value6], [...]],
                        'model_3': [[value7, value8], [...]]
                    }
            }
    """
    predictions = defaultdict(dict)
    test_labels = {tm.output_name(): [] for tm in args.tensor_maps_out if len(tm.shape) == 1}
    test_paths = []
    models = {}
    for model_file in models_inputs_outputs.keys():
        args.model_file = model_file
        args.tensor_maps_in = models_inputs_outputs[model_file][input_prefix]
        args.tensor_maps_out = models_inputs_outputs[model_file][output_prefix]

        model = make_multimodal_to_multilabel_model(args.model_file, args.model_layers, args.model_freeze, args.tensor_maps_in, args.tensor_maps_out,
                                                    args.activation, args.dense_layers, args.dropout, args.mlp_concat, args.conv_layers,
                                                    args.max_pools, args.res_layers, args.dense_blocks, args.block_size, args.conv_bn, args.conv_x,
                                                    args.conv_y, args.conv_z, args.conv_dropout, args.conv_width, args.u_connect, args.pool_x,
                                                    args.pool_y, args.pool_z, args.padding, args.learning_rate)

        model_name = os.path.basename(model_file).replace(TENSOR_EXT, '')
        models[model_name] = model

    for j in range(steps):
        input_data, labels, paths = next(generator)
        test_paths.extend(paths)
        for tl in test_labels:
            test_labels[tl].extend(np.copy(labels[tl]))

        for model_name in models:
            # We can feed 'model.predict()' the entire input data because it knows what subset to use
            y_prediction = models[model_name].predict(input_data)

            for i, tm in enumerate(args.tensor_maps_out):
                if tm in outputs and tm.output_name() in test_labels:
                    if j == 0:
                        predictions[tm][model_name] = []
                    if len(args.tensor_maps_out) == 1:
                        predictions[tm][model_name].extend(np.copy(y_prediction))
                    else:
                        predictions[tm][model_name].extend(np.copy(y_prediction[i]))

    for tm in predictions:
        logging.info(f"{tm.output_name()} labels: {len(test_labels[tm.output_name()])}")
        test_labels[tm.output_name()] = np.array(test_labels[tm.output_name()])
        for m in predictions[tm]:
            logging.info(f"{tm.output_name()} model: {m} prediction length:{len(predictions[tm][m])}")
            predictions[tm][m] = np.array(predictions[tm][m])

    return predictions, test_labels, test_paths


def _calculate_and_plot_prediction_stats(args, predictions, outputs, paths):
    rocs = []
    scatters = []
    for tm in args.tensor_maps_out:
        if tm not in predictions:
            continue
        plot_title = tm.name+'_'+args.id
        plot_folder = os.path.join(args.output_folder, args.id)

        if tm.is_categorical_any_with_shape_len(1):
            msg = "For tm '{}' with channel map {}: sum truth = {}; sum pred = {}"
            for m in predictions[tm]:
                logging.info(msg.format(tm.name, tm.channel_map, np.sum(outputs[tm.output_name()], axis=0), np.sum(predictions[tm][m], axis=0)))
            plot_rocs(predictions[tm], outputs[tm.output_name()], tm.channel_map, plot_title, plot_folder)
            rocs.append((predictions[tm], outputs[tm.output_name()], tm.channel_map))
        elif tm.is_categorical_any_with_shape_len(4):
            for p in predictions[tm]:
                y = predictions[tm][p]
                melt_shape = (y.shape[0]*y.shape[1]*y.shape[2]*y.shape[3], y.shape[4])
                predictions[tm][p] = y.reshape(melt_shape)

            y_truth = outputs[tm.output_name()].reshape(melt_shape)
            plot_rocs(predictions[tm], y_truth, tm.channel_map, plot_title, plot_folder)
            plot_precision_recalls(predictions[tm], y_truth, tm.channel_map, plot_title, plot_folder)
            roc_aucs = get_roc_aucs(predictions[tm], y_truth, tm.channel_map)
            precision_recall_aucs = get_precision_recall_aucs(predictions[tm], y_truth, tm.channel_map)
            aucs = {"ROC": roc_aucs, "Precision-Recall": precision_recall_aucs}
            log_aucs(**aucs)
        elif tm.is_continuous() and len(tm.shape) == 1:
            scaled_predictions = {k: tm.rescale(predictions[tm][k]) for k in predictions[tm]}
            plot_scatters(scaled_predictions, tm.rescale(outputs[tm.output_name()]), plot_title, plot_folder, paths)
            scatters.append((scaled_predictions, tm.rescale(outputs[tm.output_name()]), plot_title, None))
            coefs = get_pearson_coefficients(scaled_predictions, tm.rescale(outputs[tm.output_name()]))
            log_pearson_coefficients(coefs, tm.name)
        else:
            scaled_predictions = {k: tm.rescale(predictions[tm][k]) for k in predictions[tm]}
            plot_scatters(scaled_predictions, tm.rescale(outputs[tm.output_name()]), plot_title, plot_folder)
            coefs = get_pearson_coefficients(scaled_predictions, tm.rescale(outputs[tm.output_name()]))
            log_pearson_coefficients(coefs, tm.name)

    if len(rocs) > 1:
        subplot_comparison_rocs(rocs, plot_folder)
    if len(scatters) > 1:
        subplot_comparison_scatters(scatters, plot_folder)


def _tsne_wrapper(model, hidden_layer_name, alpha, plot_path, test_paths, test_labels, test_data=None, tensor_maps_in=None, batch_size=16, embeddings=None):
    """Plot 2D t-SNE of a model's hidden layer colored by many different co-variates.

    Callers must provide either model's embeddings or test_data on which embeddings will be inferred

    :param model: Keras model
    :param hidden_layer_name: String name of the hidden layer whose embeddings will be visualized
    :param alpha: Transparency of each data point
    :param plot_path: Image file name and path for the t_SNE plot
    :param test_paths: Paths for hd5 file containing each sample
    :param test_labels: Dictionary mapping TensorMaps to numpy arrays of labels (co-variates) to color code the t-SNE plots with
    :param test_data: Input data for the model necessary if embeddings is None
    :param tensor_maps_in: Input TensorMaps of the model necessary if embeddings is None
    :param batch_size: Batch size necessary if embeddings is None
    :param embeddings: (optional) Model's embeddings
    :return: None
    """
    if hidden_layer_name not in [layer.name for layer in model.layers]:
        logging.warning(f"Can't compute t-SNE, layer:{hidden_layer_name} not in provided model.")
        return

    if embeddings is None:
        embeddings = embed_model_predict(model, tensor_maps_in, hidden_layer_name, test_data, batch_size)

    label_dict, categorical_labels, continuous_labels = test_labels_to_label_dictionary(test_labels, len(test_paths))

    gene_labels = []
    plot_tsne(embeddings, categorical_labels, continuous_labels, gene_labels, label_dict, plot_path, alpha)


def _get_tensor_files(tensor_dir):
    return [tensor_dir + tp for tp in os.listdir(args.tensors) if os.path.splitext(tp)[-1].lower() == TENSOR_EXT]


if __name__ == '__main__':
    args = parse_args()
    run(args)  # back to the top