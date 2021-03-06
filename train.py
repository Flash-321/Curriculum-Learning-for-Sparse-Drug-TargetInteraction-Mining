import torch
import torch.optim as optim
import torchvision
from torch.utils.data import DataLoader
import numpy as np
import os
import shutil
from tensorboardX import SummaryWriter
from warmup_scheduler import GradualWarmupScheduler

from models.dt_net import DTNet
from data.Dataset import DrugTargetInteractionDataset
from data.datautils import collate_fn
from utils.general import num_params, train, evaluate
from utils.parser import *
from models.labelsmoothing import LabelSmoothing


def main():
    # load args
    args = parse_args()
    # set seed
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    # check device
    torch.cuda.set_device(args.gpu_id)
    gpuAvailable = torch.cuda.is_available()
    device = torch.device("cuda" if gpuAvailable else "cpu")
    kwargs = {"num_workers": args.num_workers, "pin_memory": True} if gpuAvailable else {}
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    # declaring the train and validation datasets and their corresponding dataloaders
    trainData = DrugTargetInteractionDataset("train", args.neg_rate, args.step_size, args.target_h5_dir, args.freeze_protein_embedding,
                                             edge_weight=not args.no_edge_weight, use_hcount=not args.no_hcount)
    trainLoader = DataLoader(trainData, batch_size=args.batch_size, collate_fn=collate_fn, shuffle=True, **kwargs)
    valData = DrugTargetInteractionDataset("val", args.neg_rate, args.step_size, args.target_h5_dir, args.freeze_protein_embedding,
                                           edge_weight=not args.no_edge_weight, use_hcount=not args.no_hcount)
    valLoader = DataLoader(valData, batch_size=args.batch_size, collate_fn=collate_fn, shuffle=False, **kwargs)

    # declaring the model, optimizer, scheduler and the loss function
    model = DTNet(args.freeze_protein_embedding, args.d_model, args.graph_layer, trainData.drug_dataset.embedding_dim, args.mlp_depth,
                  args.graph_depth, args.GAT_head, args.target_in_size, args.pretrain_dir, args.gpu_id, args.atten_type, args.drug_conv,
                  args.target_conv, args.conv_dropout, args.add_transformer, args.focal_loss)
    if args.curriculum_weight is not None:
        model.load_state_dict(torch.load(args.curriculum_weight, map_location="cpu"))
        print("\nLoad model %s \n" % args.curriculum_weight)
    model.to(device)
    if args.train_cls_only:
        for param in model.parameters():
            param.requires_grad = False
        for param in model.outputMLP.parameters():
            param.requires_grad = True

    # Optimizer & scheduler
    drug_net_params = list(map(id, model.drug_net.parameters()))
    other_params = filter(lambda p: id(p) not in drug_net_params, model.parameters())
    optimizer = optim.Adam(
        [{'params': model.drug_net.parameters(), 'lr': args.drugnet_lr_scale * args.init_lr}, {'params': other_params, 'lr': args.init_lr}],
        lr=args.init_lr, betas=(args.MOMENTUM1, args.MOMENTUM2))

    scheduler_reduce = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=args.LR_SCHEDULER_FACTOR, patience=args.LR_SCHEDULER_WAIT,
                                                            threshold=args.LR_SCHEDULER_THRESH, threshold_mode="abs", min_lr=args.final_lr,
                                                            verbose=True)
    scheduler = GradualWarmupScheduler(optimizer, multiplier=1, total_epoch=20, after_scheduler=scheduler_reduce)

    # Loss function
    # loss_function = nn.CrossEntropyLoss()
    if args.focal_loss:
        loss_function = torchvision.ops.sigmoid_focal_loss
    else:
        loss_function = LabelSmoothing()

    # create ckp
    if os.path.exists(os.path.join('checkpoints', args.save_dir)):
        shutil.rmtree(os.path.join('checkpoints', args.save_dir))
    os.makedirs(os.path.join('checkpoints', args.save_dir))

    # printing the total and trainable parameters in the model
    numTotalParams, numTrainableParams = num_params(model)
    print("\nNumber of total parameters in the model = %d" % numTotalParams)
    print("Number of trainable parameters in the model = %d\n" % numTrainableParams)
    print("\nTraining the model .... \n")

    writer = SummaryWriter(os.path.join('logs', args.save_dir))

    # evaluate the model on validation set
    valLoss, valTP, valFP, valFN, valTN, valAcc, valF1 = evaluate(model, valLoader, loss_function, device, args.neg_rate)
    writer.add_scalar("val_loss/loss", valLoss, -1)
    writer.add_scalar("val_score/acc", valAcc, -1)
    writer.add_scalar("val_score/F1", valF1, -1)
    writer.add_scalar("val_score/TP", valTP, -1)
    writer.add_scalar("val_score/FP", valFP, -1)
    writer.add_scalar("val_score/FN", valFN, -1)
    writer.add_scalar("val_score/TN", valTN, -1)
    print("\nStep: %03d  Val|| Loss: %.6f || Acc: %.3f  F1: %.3f || TP: %d TN %d FP: %d FN: %d" % (
        -1, valLoss, valAcc, valF1, valTP, valTN, valFP, valFN))

    for step in range(args.num_steps):
        # train the model for one step
        trainLoss, trainTP, trainFP, trainFN, trainTN, trainAcc, trainF1 = train(model, trainLoader, optimizer, loss_function, device, writer, step,
                                                                                 args.neg_rate, args.train_cls_only)
        writer.add_scalar("train_loss/loss", trainLoss, step)
        writer.add_scalar("train_score/acc", trainAcc, step)
        writer.add_scalar("train_score/F1", trainF1, step)
        writer.add_scalar("train_score/TP", trainTP, step)
        writer.add_scalar("train_score/FP", trainFP, step)
        writer.add_scalar("train_score/FN", trainFN, step)
        writer.add_scalar("train_score/TN", trainTN, step)
        print("\nStep: %03d  Train|| Loss: %.6f || Acc: %.3f  F1: %.3f || TP: %d TN %d FP: %d FN: %d" % (
            step, trainLoss, trainAcc, trainF1, trainTP, trainTN, trainFP, trainFN))

        # evaluate the model on validation set
        valLoss, valTP, valFP, valFN, valTN, valAcc, valF1 = evaluate(model, valLoader, loss_function, device, args.neg_rate)
        writer.add_scalar("val_loss/loss", valLoss, step)
        writer.add_scalar("val_score/acc", valAcc, step)
        writer.add_scalar("val_score/F1", valF1, step)
        writer.add_scalar("val_score/TP", valTP, step)
        writer.add_scalar("val_score/FP", valFP, step)
        writer.add_scalar("val_score/FN", valFN, step)
        writer.add_scalar("val_score/TN", valTN, step)
        print("\nStep: %03d  Val|| Loss: %.6f || Acc: %.3f  F1: %.3f || TP: %d TN %d FP: %d FN: %d" % (
            step, valLoss, valAcc, valF1, valTP, valTN, valFP, valFN))

        writer.add_scalar("hparam/lr", optimizer.param_groups[1]['lr'], step)

        # make a scheduler step
        scheduler.step(valF1)

        # saving the model weights and loss/metric curves in the checkpoints directory after every few steps
        if ((step % args.save_frequency == 0) or (step == args.num_steps - 1)) and (step != 0):
            savePath = args.code_dir + "checkpoints/{}/train-step_{:04d}-Acc_{:.3f}.pt".format(args.save_dir, step, valAcc)
            torch.save(model.state_dict(), savePath)

    print("\nTraining Done.\n")
    return


if __name__ == "__main__":
    main()
