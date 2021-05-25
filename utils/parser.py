import argparse


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('--save_dir', type=str, required=True)
    parser.add_argument('--code_dir', type=str, default='')
    parser.add_argument('--pretrain_dir', type=str, default='../3e_pretrain/model_weight.bin')
    parser.add_argument('--gpu_id', type=int, default=0)
    parser.add_argument('--num_workers', type=int, default=4)
    parser.add_argument('--seed', type=int, default=19260817)
    parser.add_argument('--init_lr', type=float, default=1e-4)
    parser.add_argument('--final_lr', type=float, default=1e-7)
    parser.add_argument('--LR_SCHEDULER_FACTOR', type=float, default=0.5)
    parser.add_argument('--LR_SCHEDULER_WAIT', type=float, default=20)
    parser.add_argument('--LR_SCHEDULER_THRESH', type=float, default=0.001)
    parser.add_argument('--MOMENTUM1', type=float, default=0.9)
    parser.add_argument('--MOMENTUM2', type=float, default=0.999)

    parser.add_argument('--weight', type=str, default=None)
    parser.add_argument('--neg_rate', type=int, default=5)
    parser.add_argument('--batch_size', type=int, default=64)
    parser.add_argument('--num_steps', type=int, default=200)
    parser.add_argument('--save_frequency', type=int, default=5)
    parser.add_argument('--d_model', type=int, default=512)
    parser.add_argument('--target_in_size', type=int, default=121)
    parser.add_argument('--graph_layer', type=str, default='GCN', choices=['GCN', 'GAT'])
    parser.add_argument('--GAT_head', type=int, default=2)
    parser.add_argument('--graph_depth', type=int, default=2)
    parser.add_argument('--mlp_depth', type=int, default=2)
    parser.add_argument('--no_edge_weight', default=False, action='store_true')
    parser.add_argument('--no_hcount', default=False, action='store_true')
    parser.add_argument('--model_name', type=str, default="baseline")
    args = parser.parse_args()
    print('============Args==============')
    print(args)
    return args
