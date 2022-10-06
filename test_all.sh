#!/bin/bash

source venv/bin/activate

for model_folder in "" egs/ecapa-tdnn #egs/resnet
do
  if [ -z "$model_folder" ]; then continue; fi;
  cd $model_folder || exit

  weights=$(ls ./*.pdparams)

  ## Random 1 ##
#  for dataset in VoxCeleb1 random-simulated random-lms-a1 random-nlms-a1 random-klms-a1 random-nklms-a1
  for dataset in random-lms-a1 random-nlms-a1 random-klms-a1
  ## Random 2 ##
#  for dataset in random2-simulated random2-nlms-a1 random2-nklms-a1 random2-lms-a1 random2-klms-a1
  do
    folder=/media/viniciusas/ExtremeSSD/Datasets/$dataset/test/wav
    echo
    echo "################"
    echo "TESTING MODEL $model_folder WITH DATASET $dataset"
    echo
    python ../../test.py --test_folder $folder -w "$weights" -c ./config.yaml -d gpu:0
    echo "################"
    echo
  done

  cd ../..
done
