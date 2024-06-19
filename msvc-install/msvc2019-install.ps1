
# 14.20.27525         16.0.16
# 14.21.27702.2       16.1.0
# 14.22.27906         16.2.1
# 14.23.28105.4       16.3.2
# 14.24.28325         16.4.16
# 14.25.28614         16.5.4
# 14.26.28808.1       16.6.3
# 14.27.29120         16.7.28
# 14.28.29335         16.8.3
# 14.28.29921         16.9.16
# 14.29.30040-v2      16.10.4
# 14.29.30153         16.11.33

$versions = (
    (New-Object PSObject -Property @{ Version="16.11.34931.43"; Url="https://download.visualstudio.microsoft.com/download/pr/190b8b27-9da7-49b4-bb27-75d3a5abe45e/12bddd5f9ccdaa345d5e25bc7231e52b21ed7b335f8595fa83927f98fe7aaf59/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.34902.97"; Url="https://download.visualstudio.microsoft.com/download/pr/81bda3f8-b6f6-4caa-afe1-bfaaecb5ceb7/b06a5860c2908d99687fbe01a74bb5c7fc7b0b9cd4f3587246597f7fe0444d93/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.34729.46"; Url="https://download.visualstudio.microsoft.com/download/pr/4f765eb7-6d6e-4c22-865e-111a0166d32f/88b9e53174d2b281d2e98954791a99763761089aa523605b55a47d0c23af3517/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.34601.136"; Url="https://download.visualstudio.microsoft.com/download/pr/30682086-8872-4c7d-b066-0446b278141b/6cc639a464629b62ece2b4b786880bd213ee371d89ffc7717dc08b7f68644f38/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.34407.143"; Url="https://download.visualstudio.microsoft.com/download/pr/5a378c6a-0e85-4ebe-b6c8-59490e0c210b/f97374f18266781c9a4a1060052f42a7b73b754d52a9bb989ab52bf0ac458a3f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.34301.259"; Url="https://download.visualstudio.microsoft.com/download/pr/ed573b12-f211-4911-834c-c3e3a87d7e58/2270e556c8244fc2598e764b7e740ec142b481bc7c60faf47b61c40ca6628780/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.34114.132"; Url="https://download.visualstudio.microsoft.com/download/pr/1f10f231-caa4-4ec6-ae24-bd414213cf89/2e3b9b08b2841a321e7557bd631474df15d9f7ebc14fad7515142d2e686bdaec/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.34031.81"; Url="https://download.visualstudio.microsoft.com/download/pr/9632a9a9-9059-400b-aaeb-efca72aeadd1/098a3ff9a1d3ac54c914e61c9c24e84160df30104c9fb80f447fdac2b291cca3/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.33927.289"; Url="https://download.visualstudio.microsoft.com/download/pr/996d318f-4bd0-4f73-8554-ea3ed556ce9b/9610a60ad452c33dd3f9e8d3b4ce5d88d278f8b063d88717e08e1c0c13c29233/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.33920.266"; Url="https://download.visualstudio.microsoft.com/download/pr/a97c60a8-e16e-4689-bd0f-cb5b4761fa13/75e2ad77042dd4cb80e2cc5997e4dd8a2e88f8e9f31cb009e377ed800c581857/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.33801.447"; Url="https://download.visualstudio.microsoft.com/download/pr/7c09e2e8-2b3e-4213-93ab-5646874f8a2b/73d0e76d9156e11d8d448e5da817d4d83d7a9edb12190aea4c0b6fb8af25cd2c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.33529.622"; Url="https://download.visualstudio.microsoft.com/download/pr/48ee919d-ab7d-45bc-a595-a2262643c3bc/295fdfc1de25116a75b2d6e0944284f2f79c0778ffab798ae9db35d187e8ab99/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.33423.256"; Url="https://download.visualstudio.microsoft.com/download/pr/e0881e2b-53dd-47b3-a2c1-ba171c568981/c51364831742dcd512c6cdb4a52d266215732c60202e19aede1bfdf4f141dbac/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.33328.57"; Url="https://download.visualstudio.microsoft.com/download/pr/50e007f5-f272-4bc3-a6b8-717859dae1ee/cbe1fff41ea8b57ff355b81f1afe36f94e7552343abc86ae19f8ee43c640fc9a/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.33214.272"; Url="https://download.visualstudio.microsoft.com/download/pr/33d686db-3937-4a19-bb3c-be031c5d69bf/66d85abf1020496b07c59aba176def5127352f2fbdd3c4c4143738ab7dfcb459/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.33130.400"; Url="https://download.visualstudio.microsoft.com/download/pr/486c4251-9333-4264-a38e-47174e8e8c0d/b91bdb0947b5ae4271db75524fde5bf349547780f6532bee553a478ff6899f4d/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.33027.164"; Url="https://download.visualstudio.microsoft.com/download/pr/8f1eb024-006a-43f6-a372-0721f71058b3/cc5cc690ac094fbfa78dfb8e40089ba52056026579e8d8dc31e95e8ea5466df5/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32929.386"; Url="https://download.visualstudio.microsoft.com/download/pr/e84651e1-d13a-4bd2-a658-f47a1011ffd1/05dbd1f3ab48fb4ec86c1db193f6a96aa9a3e7d94fdc29132f2efe12f329ac58/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32901.82"; Url="https://download.visualstudio.microsoft.com/download/pr/6d7709aa-465b-4604-b797-3f9c1d911e67/bf33ca62eacd6ffb4f9e9f8e9e72294ed2b055c1ccbd7a299f5c5451d16c8447/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32802.440"; Url="https://download.visualstudio.microsoft.com/download/pr/e33403d5-ac1e-4600-b624-d59ccd7b9a13/1eef902363a18c6b3f6ee7aed27611e0e1671942bb937891c44fbb54fba6b7fb/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32630.194"; Url="https://download.visualstudio.microsoft.com/download/pr/d59287e5-e208-462b-8894-db3142c39eca/d5b3a9695dfd9f13cbf3ffdbbcc66abc5e8cb36f61f1042141f4cd5993aa89a4/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32602.291"; Url="https://download.visualstudio.microsoft.com/download/pr/b29e5b57-df7c-4e38-acaf-5f8187a76fd0/1345ca588d22a3a5373e62c7d0ba3458d05422c24136e04846754086e252b431/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32510.428"; Url="https://download.visualstudio.microsoft.com/download/pr/d6eda263-3327-488b-9ed7-ecf65d1a6ada/8e4ae49512d22fda08c439751da9a7729abab1690065da16dbd9f0b0f17bac61/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32428.217"; Url="https://download.visualstudio.microsoft.com/download/pr/f4685935-e4ae-4242-93bc-38dbe6477fb9/235d263c0b61c75da5c79938ad70e7fe67c83ed0d9bca7773ddc50a74c9dcc59/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32413.511"; Url="https://download.visualstudio.microsoft.com/download/pr/d935ace6-0b55-4ef2-8ef2-7921ad9f3d3a/e2dec25f47d3abe13a0874e91d4eede0bfd67adc07d8bf23761b12e81c89bb81/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32407.337"; Url="https://download.visualstudio.microsoft.com/download/pr/890a2f3f-4222-451c-b7ea-035d6c583dd7/11a323cd2efd2fc6ea81332e21904cfc703ca1ab80ff81b758877f99b5d7402d/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32228.343"; Url="https://download.visualstudio.microsoft.com/download/pr/73f91fcb-aa18-4bec-8c2f-8270acb22398/775c32ca5efcdc1e2227e52e943bb05bc8a7a9c1acacebb9d4ccc8496cc9906c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32126.315"; Url="https://download.visualstudio.microsoft.com/download/pr/791f3d28-7e20-45d9-9373-5dcfbdd1f6db/d5eabc3f4472d5ab18662648c8b6a08ea0553699819b88f89d84ec42d12f6ad7/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32106.194"; Url="https://download.visualstudio.microsoft.com/download/pr/9a26f37e-6001-429b-a5db-c5455b93953c/f1c4f7b32e6da59b0a80c3a800d702211551738bcec68331aee1ab06d859be3d/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.32002.261"; Url="https://download.visualstudio.microsoft.com/download/pr/b763973d-da6e-4025-834d-d8bc48e7d37f/4c9d3173a35956d1cf87e0fa8a9c79a0195e6e2acfe39f1ab92522d54a3bebb9/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.31911.196"; Url="https://download.visualstudio.microsoft.com/download/pr/c91ba3a2-4ed9-4ada-ac4a-01f62c9c86a9/5dc5c6649b2d35ab400df8536e8ee509304e48f560c431a264298feead70733c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.31829.152"; Url="https://download.visualstudio.microsoft.com/download/pr/f1e43525-cd53-4012-9644-d7846e2c4963/9eb84f3bf5695fd108713fb15b827fe3755fc7c9ea3fa78eb83ed40015fd866b/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.31729.503"; Url="https://download.visualstudio.microsoft.com/download/pr/5a50b8ac-2c22-47f1-ba60-70d4257a78fa/4e0f5197da02b62b9fa48f05b55f2e206265785a6f0bab7235ef88fbdbe49e5e/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.31727.386"; Url="https://download.visualstudio.microsoft.com/download/pr/1051e775-b2c9-4b7a-a227-1e60bffe102a/ea5ad34fa76d6410e8200fce285005dafb683eadb767a927ebba56532fbd720f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.31702.278"; Url="https://download.visualstudio.microsoft.com/download/pr/22c17f05-944c-48dc-9f68-b1663f9df4cb/f3f6868ff82ea90b510c3ef76b8ee3ed2b559795da8dd80f3706fb8a7f7510d6/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.31624.102"; Url="https://download.visualstudio.microsoft.com/download/pr/bacf7555-1a20-4bf4-ae4d-1003bbc25da8/e6cfafe7eb84fe7f6cfbb10ff239902951f131363231ba0cfcd1b7f0677e6398/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.31613.86"; Url="https://download.visualstudio.microsoft.com/download/pr/9efbe138-ff42-4deb-95c9-1d78cdc1f98b/920981c883089c445a6a3a617396d089e7999437c1d70fc4629f557a75ac4fa5/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.11.31605.320"; Url="https://download.visualstudio.microsoft.com/download/pr/45dfa82b-c1f8-4c27-a5a0-1fa7a864ae21/75e7f5779a42dddabc647af82a7eae4bf1417484f0cd1ac9e8fd87cbe7450c39/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.10.31515.178"; Url="https://download.visualstudio.microsoft.com/download/pr/acfc792d-506b-4868-9924-aeedc61ae654/72ae7ec0c234bbe0e655dc4776110c23178c8fbb7bbcf9b5b96a683b95e8d755/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.10.31424.327"; Url="https://download.visualstudio.microsoft.com/download/pr/9dc321fd-8a9b-47ef-98a9-af0515e08d6f/722879b06e5570c1695878a24e7b46ca4f3ec53fe016826c02a452f8a5e7df0b/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.10.31410.357"; Url="https://download.visualstudio.microsoft.com/download/pr/2d4f424c-910d-4198-80de-aa829c85ae6a/4bead7a72a5cb6bf93b8e59d297d84e47da9ae2f9f44033c1ae1ef377078c5aa/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.10.31402.337"; Url="https://download.visualstudio.microsoft.com/download/pr/5c44c598-f77e-4815-89ca-e7a1f87c579a/904a77de140c9f2a5c423e57d0eebe4aee00836816c6afa1b81ffba22c0d2aac/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.10.31321.278"; Url="https://download.visualstudio.microsoft.com/download/pr/cb1d5164-e767-4886-8955-2df3a7c816a8/b9ff67da6d68d6a653a612fd401283cc213b4ec4bae349dd3d9199659a7d9354/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.32930.78"; Url="https://download.visualstudio.microsoft.com/download/pr/245e99d9-73d8-4db6-84eb-493b0c059e15/b2fd18b4c66d507d50aced118be08937da399cd6edb3dc4bdadf5edc139496d4/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.32901.84"; Url="https://download.visualstudio.microsoft.com/download/pr/673b6618-f54a-442c-86ca-35b825a86c54/8c213d29d2faa3d696d84b0ca89ecc6717e61a79c40a44613feb6c7ab87ea951/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.32802.399"; Url="https://download.visualstudio.microsoft.com/download/pr/bbebea41-0f4f-4d02-95d2-23041e9e2114/ee6204169ef3d6b8e720e4732dc69a68ddaa4c32f90016034698cb6006de0582/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.32630.195"; Url="https://download.visualstudio.microsoft.com/download/pr/ab7b6eaa-e620-480e-b532-767a689ae7c7/7bfcf3dcbec0d0b7f11e9e01bdbdbce78bd383e1aece9835490e02b76a35a70c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.32602.290"; Url="https://download.visualstudio.microsoft.com/download/pr/1b04f9e9-4618-4584-8dce-ba6554dbfd68/b09de7d3567624583571e471b7c7a1133cca074242e7f9f97c98e48d86422f28/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.32428.249"; Url="https://download.visualstudio.microsoft.com/download/pr/da393795-3f89-4db4-a682-5e5ff27dd33f/9febc4397ee2b10d7e8f00bb8847ea55c086cca6280e61b68bd3915111c46581/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.32413.69"; Url="https://download.visualstudio.microsoft.com/download/pr/a2c994bc-fda6-4a57-8070-bdc290d31be5/b2bfae48d7ceb2f1b306c9d5a87d6fd0fa4be58c638b76d9247b498aa79ededa/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.32407.336"; Url="https://download.visualstudio.microsoft.com/download/pr/7792710d-73ea-4be2-933c-23b564b5902f/fc224fc924147bff31c36f21fc151f7b7f339069264aa5c14244b3629fb778a0/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.32228.547"; Url="https://download.visualstudio.microsoft.com/download/pr/d06b357b-3d84-49ac-acc4-68ed90dc799f/ca1d6619a5414c67c290daf248dafbd402e5bf33cd92ecf0e3d94252fad4da20/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.32126.311"; Url="https://download.visualstudio.microsoft.com/download/pr/6018563e-3c0d-4b71-ab5b-9560a207eaaf/4f3f37607ebd5af7929b248e3ada96dc42e7d80751075df345fa1dd366738a76/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.32106.192"; Url="https://download.visualstudio.microsoft.com/download/pr/754d6abc-254f-4a84-af35-7235fd59d9de/d98b0a8c95c6f1ba57b2de4d5a78064798412c8e9ce5f177d67581a9e27283dc/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.32002.222"; Url="https://download.visualstudio.microsoft.com/download/pr/73cf61ac-3df5-4132-9aa3-3e61ebd747da/cc1ca503602396f69fb3a93022f72c4ac813c69dff1813b8edce11ff05943605/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31910.168"; Url="https://download.visualstudio.microsoft.com/download/pr/33439e30-02ff-417f-b6ef-927e424e84c9/cff2eb1a766df58fa77a9a89e7fc1765cc419c3175cd26bb0c97806649ab0981/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31828.109"; Url="https://download.visualstudio.microsoft.com/download/pr/f9e95b5b-7e17-4df8-b335-f3633e62f7af/ac1bd6595d766ae8c439e6eddee79799663ea4b87c8c0e41c68a9ac984bc2bc9/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31728.308"; Url="https://download.visualstudio.microsoft.com/download/pr/dcb0a070-a0c3-4fda-a07e-b00b4f777924/0f7200f381b269441a113ba7bf310c4dd291ffcc9e62d0a934dc9343add96a98/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31702.126"; Url="https://download.visualstudio.microsoft.com/download/pr/e2bef28a-75a0-4e9f-895b-c5d2fb864b1e/b8e7efd9773b0676cb9e95f2bf60e11a8dcaf29dc28a85a4bf70b9835bb12a58/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31529.145"; Url="https://download.visualstudio.microsoft.com/download/pr/3daa9785-bfd4-4cb1-bdc3-6d8d52159671/b24f75623e522f42ef6c5668bdb1683f7af3cfca48cddef77d0ead38207de802/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31501.217"; Url="https://download.visualstudio.microsoft.com/download/pr/fad09826-8da6-4da2-be25-0e5395af4175/c51d3595c232bf00e364cfb3bfe71379fa05a94b9fc9385bfc0c70055cfec4bf/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31409.214"; Url="https://download.visualstudio.microsoft.com/download/pr/9b757330-0648-444e-ae56-1d1d75f69471/8f74956bce36df73e8a036a938acba71b9cecb870fab70b0d35b1472c7bded57/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31328.270"; Url="https://download.visualstudio.microsoft.com/download/pr/02b250ce-8071-4858-9111-562c12bc7fb0/3d39751acf1a49903c477a7c8c8f2c18b7992dc933887c11c7d70d56ff37cdde/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31313.79"; Url="https://download.visualstudio.microsoft.com/download/pr/e730a0bd-baf1-4f4c-9341-ca5a9caf0f9f/9a5f58f745e70806220238cb31d9da147462331eaa6ff61af1607052010b20e0/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31229.75"; Url="https://download.visualstudio.microsoft.com/download/pr/9665567e-f580-4acd-85f2-bc94a1db745f/3580c7d8c43782aebab3af6db6e46e0f89752a96336f9518d3a10f407f4048af/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31205.134"; Url="https://download.visualstudio.microsoft.com/download/pr/3105fcfe-e771-41d6-9a1c-fc971e7d03a7/e0c2f5b63918562fd959049e12dffe64bf46ec2e89f7cadde3214921777ce5c2/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31129.286"; Url="https://download.visualstudio.microsoft.com/download/pr/1fbe074b-8ae1-4e9b-8e83-d1ce4200c9d1/9a36caee9dcfaf6adcff6a96f0a3089689cb966491de6746415196c0181bcd94/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31112.23"; Url="https://download.visualstudio.microsoft.com/download/pr/1192d0de-5c6d-4274-b64d-c387185e4f45/c9cc192eb63bbdf2b29ce7a437a629b7ef83accf11c34a4eabb1faf2cb7f35b4/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31105.61"; Url="https://download.visualstudio.microsoft.com/download/pr/308e891b-f15e-43d8-8cc1-0e41f4962d4b/f3aae428387b490b55a1bb6527b7cb985a7d73eb5bf9e59cb55f01ca8c1cb0b4/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.9.31025.194"; Url="https://download.visualstudio.microsoft.com/download/pr/5c555b0d-fffd-45a2-9929-4a5bb59479a4/68c048e8c687ed045d1efd3fdc531e5ce95c05dc374b5aaaeec3614ca8ed2044/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.8.31025.109"; Url="https://download.visualstudio.microsoft.com/download/pr/092646b7-3fd5-40c0-b3ba-33c9efc89f8e/0b4407ccb32e24a47e25392a0230227e577698231db15638f6b92cadf275eca5/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.8.31019.35"; Url="https://download.visualstudio.microsoft.com/download/pr/8aaeb3c2-46bb-4444-9ca6-0361b60b2d16/1f4552565c70ee4355fcb4bf561b11dc23ae0a20cb6b4bcd0546d6819e545eae/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.8.31005.135"; Url="https://download.visualstudio.microsoft.com/download/pr/20130c62-1bc8-43d6-b4f0-c20bb7c79113/145a319d79a83376915d8f855605e152ef5f6fa2b2f1d2dca411fb03722eea72/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.8.30907.101"; Url="https://download.visualstudio.microsoft.com/download/pr/3a7354bc-d2e4-430f-92d0-9abd031b5ee5/51d0c7235e474051f0605cfe54d28d7e20017d8a97bb3aebd09d573c370b0d14/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.8.30804.86"; Url="https://download.visualstudio.microsoft.com/download/pr/9b3476ff-6d0a-4ff8-956d-270147f21cd4/0df5becfebf4ae2418f5fae653feebf3888b0af00d3df0415cb64875147e9be3/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.8.30717.126"; Url="https://download.visualstudio.microsoft.com/download/pr/9d2147aa-7b01-4336-b665-8fe07735e5ee/61cc248a8f240911db3e7ae5f0d0cd7358211d9a9424202e7a69786bb6d34357/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.8.30711.63"; Url="https://download.visualstudio.microsoft.com/download/pr/2f4a234d-6e7c-4049-8248-6d9ac0d05c96/11f7d9f212a5195ed9680cda0baddced4eb99d06762c769163498344fa239d5b/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.8.30709.132"; Url="https://download.visualstudio.microsoft.com/download/pr/5f914955-f6c7-4add-8e47-2e090bdc02fa/3e656a35dbfd21ddf7e4e5dfe46de2fb658f9bad42bfed304a92eed4d50a965f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.32413.119"; Url="https://download.visualstudio.microsoft.com/download/pr/2282640c-c74e-4d6a-9710-4eb8fef730e6/dfa5c24fb7aa4d11bf375bd2a46d19d3a1ff907cbc88468b0a50e3d71d53f77a/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.32407.390"; Url="https://download.visualstudio.microsoft.com/download/pr/324f7e64-4d92-44ae-bd4a-a65a9a31155c/d90931f12360796d48a9d8390dd261982dc6427013543e92ff1c877bdaafd524/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.32228.349"; Url="https://download.visualstudio.microsoft.com/download/pr/b7631e90-8ea9-4d5f-bbac-a1ff50515198/730348f0177bf04c6b19517ec4728a371260b5aa0a85721e57ebd4ce7b7548f5/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.32125.265"; Url="https://download.visualstudio.microsoft.com/download/pr/9d220693-473b-422a-a1b6-f14ec05eae46/a08af5df3f198b8595ddd606337808cd84e42e6b7676b41b267b8f69d8c1fcfe/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.32105.279"; Url="https://download.visualstudio.microsoft.com/download/pr/3fdc79a1-fddd-492c-a021-3e8c9fdc6c68/3251f437f9615447049bfe96af07fd642c7370a96683b526a64b3258ed53d16f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.32002.127"; Url="https://download.visualstudio.microsoft.com/download/pr/aecc97c3-8e8b-4d37-b159-d7b564f6b2b2/b34652a6159f8ea01270727c25beadab5947bd7be098ba3301271867aa6fbd2d/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.31910.167"; Url="https://download.visualstudio.microsoft.com/download/pr/1b84f336-1975-40b8-9e23-e910839dafe0/6afa8b5bacce40c17c5dea11539af890113c356b63b4ae3b1b29337530436b01/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.31828.227"; Url="https://download.visualstudio.microsoft.com/download/pr/097eb5ce-58c8-4b31-97c6-ccce4bb72113/3b7feaf1d970d3845e5fd01bd7f1dad8480c19b885bb65aaef1fd34582a419e8/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.31727.298"; Url="https://download.visualstudio.microsoft.com/download/pr/8372a5df-9781-4a47-beda-ce835a6c139a/b40c06114268635d38e9202f269731ac575f03f0ec90b3e444c571e0ef41c4d0/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.31701.349"; Url="https://download.visualstudio.microsoft.com/download/pr/a705f77f-ec9b-4b7e-86bb-d3a3c4752451/634096cbc8c01b810a12d6d945133af8bb8642ef986a1e6fec8c1bd1c6029c05/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.31528.273"; Url="https://download.visualstudio.microsoft.com/download/pr/101e05b3-94a6-4fd6-a710-b2476dc2d50b/42fd488e3831f08397e004a5c219bfee381e39fa15fdf79391285ca11baafc1f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.31429.392"; Url="https://download.visualstudio.microsoft.com/download/pr/ebe80743-8f09-4148-8ec4-04d8c889ff84/636d643d7cb222360580e21d1c365c99942bfeec61ffeac8e8ba12e3f31032ac/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.31327.30"; Url="https://download.visualstudio.microsoft.com/download/pr/8ff234c7-8df9-45cc-bfa1-614164306503/c69a90c9803fc337d6ca17b92687f3fe4a3fb8befbb007dac78112bdf2f73de3/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.31229.181"; Url="https://download.visualstudio.microsoft.com/download/pr/027ff210-d6f8-43f4-be63-3316e2aa6ce2/70b89caa3ed83c95c4dde0c7dfbd1e65b4d30815e2a4f9fbba11aa1debb4e680/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.31205.176"; Url="https://download.visualstudio.microsoft.com/download/pr/cb083d4f-5a1d-4e1a-8a2f-f2f9c8e852db/adb13e791f2a2966eee5949676df112e66efb5dd80fd8e8696fc4a4958e1eb55/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.31026.100"; Url="https://download.visualstudio.microsoft.com/download/pr/2ec789bf-8124-40f4-8b3e-3bbcdf0a8cfc/ed2d2145a42aecf6036d289ed86fce1ba1f9175e2c14eff5a2e8fcd9695d3c45/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.31009.191"; Url="https://download.visualstudio.microsoft.com/download/pr/71793757-2fcc-4144-b54e-23cecf1249b0/da79ad763dba90cfaa71176d4d047c0a688a2965fa81d111f58005daa6fc55b1/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.30928.143"; Url="https://download.visualstudio.microsoft.com/download/pr/228de158-b53e-4bbf-bec2-bae43f94668d/bbd6ea5523e14c22ffe336d6acd110d1dc56fdb73c7bfa695a682119dec73913/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.30816.78"; Url="https://download.visualstudio.microsoft.com/download/pr/fd0b4484-1a13-48cb-a0c3-398aa45a4382/44f6322c54305aab47b071ecd3b9efd599f41a4c153d2084cdff52c19c8b9479/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.30802.117"; Url="https://download.visualstudio.microsoft.com/download/pr/21e72f81-8e59-4e73-b244-b5ab994d7573/48045cb57586de2d3c0a3f658271f3dee6d40eb802683ddf94e3debc0738e734/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.30704.19"; Url="https://download.visualstudio.microsoft.com/download/pr/1206a800-42a6-4dd5-8b7d-27ccca92e823/cf739d701898f888a4c0b49722791e5ff450d40c6a986f69ecfb1e4da384e126/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.30621.155"; Url="https://download.visualstudio.microsoft.com/download/pr/a319c7ec-a0bd-4619-b966-4c58a50f7c76/8ba9f0872faf7640709098adbd88f156902529de9032d214844bec363865d99e/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.30611.23"; Url="https://download.visualstudio.microsoft.com/download/pr/6b655578-de8c-4862-ad77-65044ca714cf/eb69a008b2fa89b91c20ef09aef64525104b7863078a327324b4389f55c546d6/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.30523.141"; Url="https://download.visualstudio.microsoft.com/download/pr/e8bc3741-cb70-42aa-9b4e-2bd497de85dd/f3713de3e01b7829d529f67d6240116b73cc0743974bb5373a052f9629cc24d2/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.30517.126"; Url="https://download.visualstudio.microsoft.com/download/pr/6c56603d-6cb9-4f23-8d58-dcc8eb8b3563/1c4b90a8d28fa9f524415dac5a45066ba6f52f1049975f9637fa1d713fa7f162/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.30503.244"; Url="https://download.visualstudio.microsoft.com/download/pr/44fbb1ed-c06e-41c9-bc39-3d7f2083d61b/f860b197d3b8c07a1e59a49df13244a034b4a56693087bd8aabc440d9f989c7b/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.30413.136"; Url="https://download.visualstudio.microsoft.com/download/pr/befdb1f9-8676-4693-b031-65ee44835915/ffd743061c54a94cc93c41f944b139f31d1294a532626e0bce6e944c5284f0e6/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.30406.217"; Url="https://download.visualstudio.microsoft.com/download/pr/e3850c73-59c6-4c05-9db6-a47a74b67daf/a673e9459f6989d54a1d9b720a37386c18010757fe63840808daf0836d31ef7c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.7.30330.147"; Url="https://download.visualstudio.microsoft.com/download/pr/584a5fcf-dd07-4c36-add9-620e858c9a35/db7bb08710348d6aeade52a30d9bd0987cebb489fdea82c776416128e14eb69f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.6.30320.27"; Url="https://download.visualstudio.microsoft.com/download/pr/067fd8d0-753e-4161-8780-dfa3e577839e/4776935864d08e66183acd5b3647c9616da989c60afbfe100d4afc459f7e5785/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.6.30309.148"; Url="https://download.visualstudio.microsoft.com/download/pr/c10c95d2-4fba-4858-a1aa-c3b4951c244b/3cd935283a13a71acfdb5ee3ee413714e363207bed98351f377ba97abdb706fe/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.6.30225.117"; Url="https://download.visualstudio.microsoft.com/download/pr/408ac6e1-e3ac-4f0a-b327-8e57a845e376/b5a86361970b30160c73421f8d234249d86ce399d3ae8d011e14bd82d1435d50/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.6.30204.135"; Url="https://download.visualstudio.microsoft.com/download/pr/df6c2f11-eae3-4d3c-a0a8-9aec3421235b/283cfe5df528b05d41b2104ed091271424cab320ef00ff8c55cb586878e41a9a/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.6.30128.74"; Url="https://download.visualstudio.microsoft.com/download/pr/17a0244e-301e-4801-a919-f630bc21177d/344ccda4da2405de95961a3ee35ee8e09184dd1615238d1dc538c65bb24bf077/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.6.30114.105"; Url="https://download.visualstudio.microsoft.com/download/pr/0fed0c12-ccd3-4767-b151-a616aaf99d86/2d180d9c6b8d24f38a88301652581793353d0ffa0d9f04f6dff5ad26d720a97b/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.5.30104.148"; Url="https://download.visualstudio.microsoft.com/download/pr/68d6b204-9df0-4fcc-abcc-08ee0eff9cb2/17af83ed545d1287df7575786c326009e459708b60a6821d2a4f5606ef8efb9e/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.5.30011.22"; Url="https://download.visualstudio.microsoft.com/download/pr/5e397ebe-38b2-4e18-a187-ac313d07332a/8c101cfb67c676175074c5db3e28b58fafcd41ec00fa9db0ba321336829bfea1/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.5.30002.166"; Url="https://download.visualstudio.microsoft.com/download/pr/ac28b571-7709-4635-83d0-6277d6102ecb/447dce91b78487503d9b371d28f3f63cf63bf976c80298b3c51367129d1c99ad/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.5.29926.136"; Url="https://download.visualstudio.microsoft.com/download/pr/220fe621-dd35-4fc0-a32e-10ff6f4551cd/536047d908526e1b26bb013be794be99c40f507ebebd3750db595d8bf42331d8/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.5.29920.165"; Url="https://download.visualstudio.microsoft.com/download/pr/69b51b7f-ea5e-4729-9e7e-9ff9e2457545/cdfa3a2aa5c083800b3fe85f59a566da8f445c27e5eb5a679639ab1faf8b35ba/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.5.29911.84"; Url="https://download.visualstudio.microsoft.com/download/pr/c650b629-fb28-4b7a-b943-1d293b185299/2dcd24c40e00b11df44d2b646833ba22d1cee73aed25ba3de020ca710df0addb/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.31728.76"; Url="https://download.visualstudio.microsoft.com/download/pr/864470e6-2c8e-4dee-b2f0-c527af35237a/a68677bddba9cf0cccd838a5413fa8254333234d59c9e9094cb9e3cb015d9996/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.31701.291"; Url="https://download.visualstudio.microsoft.com/download/pr/18c1e8d7-f2b8-49af-8c36-94663b350614/f469ef859e90796edcefcb6744c61e9debd83fbe0f2ed777d56e777cbc03cabe/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.31528.272"; Url="https://download.visualstudio.microsoft.com/download/pr/4712df6a-c556-42df-8ad9-b058561ee18a/58f6009940a20c716d17e34e172fc9003582148254572a00ab76cb86e91efa5b/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.31429.391"; Url="https://download.visualstudio.microsoft.com/download/pr/755cef87-e337-468d-bc48-7c0426929076/90deefbf24f4a074ea9df5ee42c56152f7a57229655fe4d44477a32bb0a23d55/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.31327.141"; Url="https://download.visualstudio.microsoft.com/download/pr/801b46a0-5823-4800-bc54-a112bcfa0456/2d80a1489f579034177466c5e7343c87e2888ceedb66c401cc6065c2896a5c04/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.31229.387"; Url="https://download.visualstudio.microsoft.com/download/pr/212eeaaa-c6cd-43e9-832d-acf49bd54e40/b24156deaa7ce348092ba925071d94bf2517116c1a0604edb65c84060c7c9ff4/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.31205.175"; Url="https://download.visualstudio.microsoft.com/download/pr/3a315a51-8491-4d1a-bb71-f9216a12c6a9/0a4466e4544d6588ccd30290cf11431e9a918b8cdca9450b724fd23f5530dead/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.31026.101"; Url="https://download.visualstudio.microsoft.com/download/pr/d45650b3-efad-4faf-9378-de649ed5840c/d5f83a794582f8ac84269d09a5bf1ee9457131ec21dff4ca951bc6027bdce319/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.31009.304"; Url="https://download.visualstudio.microsoft.com/download/pr/1008261e-8fdf-40bf-a5d9-5d2cab1dd9c5/41ce2543c7e6dec429f41a298392a5fe8fdf53ec03cc0f88b231cf43f76f5367/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.30928.142"; Url="https://download.visualstudio.microsoft.com/download/pr/bb160f7d-817b-4976-9618-dfa86566c110/2ff4b05ce8c69c82910313a09771085a44579720e0e2675b775b9fd03b11e8c1/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.30816.121"; Url="https://download.visualstudio.microsoft.com/download/pr/0f365ec8-eea2-4166-94d2-995d546e3542/a0b4246fba2caedb0c49b628d6fdff25e3b124c2652824c296fffe2b90fffa71/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.30802.185"; Url="https://download.visualstudio.microsoft.com/download/pr/f0d6fe7d-6d3d-4bed-8c93-30d04d146d79/e92aa7a8dedfe4c92c727c779809b4ba2b1b007599455e41b1a22c3397e248f6/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.30703.110"; Url="https://download.visualstudio.microsoft.com/download/pr/dc078c52-0884-43b0-ad20-1cff9a4ded0b/d0103a2d1e3ad06e0c4bd146824ca5cffd357a3010a471b147a441aba16b8fbd/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.30607.51"; Url="https://download.visualstudio.microsoft.com/download/pr/b023937e-17e1-40e6-a459-3e68c7368d38/3a0e850c0036d475da3a58fb27eeec0fd2f005dbf33a8eb1a92ff347959e7552/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.30427.197"; Url="https://download.visualstudio.microsoft.com/download/pr/5180f680-9135-47a5-ad38-1a76105af2c5/1669daaf354afe46df5435cd4eaf06b6366c1c22261956618c361e4c90b2bb72/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.30406.169"; Url="https://download.visualstudio.microsoft.com/download/pr/bce0cae5-3c2f-484d-b4a7-08d4d82d7469/ce5e305a06dba0ae7c709e43c1b28fdecee23fbbd2891cd7c9c21c055c09c268/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.30308.118"; Url="https://download.visualstudio.microsoft.com/download/pr/507100c1-8d44-49f2-9085-6c45f29f8ab2/d24c6a651c1c27e6a5f0013e653705fd8c740db49881cadfa3cb3f29da014deb/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.30204.51"; Url="https://download.visualstudio.microsoft.com/download/pr/ea8e5482-7fb2-47dc-9006-503d0ed2067b/539b4bcf9ca3ab48bf6203ca2c26998a4ccb3c40ebaee63ea295fce8bd108035/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.30120.98"; Url="https://download.visualstudio.microsoft.com/download/pr/f5b9c402-9bbf-4356-818e-ef7e6d162f94/33753352fb5bbc397b6e9400515a9d9e2a62b280de14837cee302fa9ed0b1106/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.30107.140"; Url="https://download.visualstudio.microsoft.com/download/pr/1cac10bc-3584-491f-95ef-a7671dd5805a/23b22b1672ddb423161e64a2319926cb75097628beeb7337aa681f82580f7176/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.30011.19"; Url="https://download.visualstudio.microsoft.com/download/pr/5558fe66-58d5-430f-bea2-0a253f6682ab/aa8bd8b72a49e4172cdbb10c90a2f9bac7eb6a666d536409ba8c2202d2874898/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.29905.134"; Url="https://download.visualstudio.microsoft.com/download/pr/5714a1fb-d8a9-4e24-b6b7-c1a40a001d4c/f68093ddf8d523354d63ac326697473c98439c92c7df09159fe974ea6622b2f5/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.29806.167"; Url="https://download.visualstudio.microsoft.com/download/pr/378e5eb4-c1d7-4c05-8f5f-55678a94e7f4/b9619acc0f9a1dfbdc1b67fddf9972e169916ceae237cf95f286c9e5547f804f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.29728.190"; Url="https://download.visualstudio.microsoft.com/download/pr/8ab6eab3-e151-4f4d-9ca5-07f8434e46bb/df2db8df6dbb2d9c22aa627ce065811926a7396cb7c8e421c1dd865aba2cf231/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.29709.97"; Url="https://download.visualstudio.microsoft.com/download/pr/b79d5d47-f792-4eec-adcf-2da2dfa3e3db/843084ba73be78a738be2993768536a974d68a9391fe458902bb010d1075e5fe/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.29613.14"; Url="https://download.visualstudio.microsoft.com/download/pr/f6473c9f-a5f6-4249-af28-c2fd14b6a0fb/908c4cb0b90d42c9cb6d22b3e21dd50111aea046c7c4636b88ba9d7c888f4aeb/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.29609.76"; Url="https://download.visualstudio.microsoft.com/download/pr/449a624c-a30d-4cc3-b971-fcf6a375a8c5/48b4e76874f597047bf53540e686b29fdb5a5950bfef2e450eeec51fe836375e/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.4.29519.181"; Url="https://download.visualstudio.microsoft.com/download/pr/c7d8bceb-64c4-426d-85a2-89bc21b21245/27777a3b4c1c200f4a9cf819a2f44e32c9cd7e851faef80a0817cfbea69cbaa3/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.3.29519.87"; Url="https://download.visualstudio.microsoft.com/download/pr/5446351f-19f5-4b09-98c6-a4bfacc732d7/3cec278012466e87b76be170de3f881e3c14be52bf8eaa3b8c464dbeee3b4fef/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.3.29509.3"; Url="https://download.visualstudio.microsoft.com/download/pr/57d28351-e762-4ee1-aca4-16b6d3faaa33/8e71c0da812dbec7ccd8d957a21d4d8ffea0b9c1b42ecc906e0c90ef3d6757f6/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.3.29503.13"; Url="https://download.visualstudio.microsoft.com/download/pr/e58a94db-93b0-4173-b26b-fc5f5c1bef7a/a74fc0d790a5844f8e966764cf2d5cf0980dd33dfa508dcabe1da4d8890950ee/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.3.29424.173"; Url="https://download.visualstudio.microsoft.com/download/pr/d1553812-31d4-46b0-a480-e6b965eb1125/f4dc35da4f4d6608efa5025511d015c5803fa1df4ff14400b5141c0be050a940/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.3.29418.71"; Url="https://download.visualstudio.microsoft.com/download/pr/f4e14058-49e0-457c-b3cf-f14e6f2f073e/ca68e100eaee172c84e229c9fa9bbff9acb11fd8ad44eca0de04a79f0e61c0fe/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.3.29411.108"; Url="https://download.visualstudio.microsoft.com/download/pr/affe0a26-d4e9-4a1e-8e58-6c7061389fac/d2802cf8f7a72e70afa82aceda7d47563061f1b74ee56b50d1f0c1d8a92be9a2/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.3.29409.12"; Url="https://download.visualstudio.microsoft.com/download/pr/4d126267-ec77-4e11-9e40-e5576d6a4510/a3817881b43d1ace0c1d4fb351b1c67baecfef523e3417b6b6444fa6a4e88beb/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.3.29403.142"; Url="https://download.visualstudio.microsoft.com/download/pr/7a31a891-eec2-4d8e-ae4e-f63b8b3ad3be/3713529f4e1df1c24fb2a73b9b2e2bf78c9d17c2888f8cec88ceadc488afdab5/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.3.29326.143"; Url="https://download.visualstudio.microsoft.com/download/pr/02aebac1-9464-4473-9af5-710a97b8f023/d58e0cfb9fadf8486dfdcf808b07f2fe7d4300b3334576885ba8f7f6bf0f2e0c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.3.29324.140"; Url="https://download.visualstudio.microsoft.com/download/pr/d7691cc1-82e6-434f-8e9f-a612f85b4b76/c62179f8cbbb58d4af22c21e8d4e122165f21615f529c94fad5cc7e012f1ef08/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.3.29318.209"; Url="https://download.visualstudio.microsoft.com/download/pr/1d102ee6-9263-4353-8676-6430f0cc5998/16693d20c56cd17d25537fd3b8c75ce6f81c6cd0e320bae8e330585046707013/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.2.29306.81"; Url="https://download.visualstudio.microsoft.com/download/pr/c4fef23e-cc45-4836-9544-70e213134bc8/e2d78bee4190c76ec43c1b9e1ebef6fc82e9271ee635ddc0de166bd9bc30086a/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.2.29230.47"; Url="https://download.visualstudio.microsoft.com/download/pr/f7e4b23c-a833-4926-a096-881a57b4cff2/46215d4e73cd15e9ff7f00cada35ff95cfb41c388cc537bdf7816b0b10d7f95d/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.2.29215.179"; Url="https://download.visualstudio.microsoft.com/download/pr/51421349-82ef-4d4c-959b-e8ff7369c54a/3af12a9a0bb45a384a0b8989803f0d63/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.2.29209.62"; Url="https://download.visualstudio.microsoft.com/download/pr/83e66bd5-ee66-4e8e-9f39-d0e7e2d3cb77/7356964e68a03ef53523e96cbe1d96d3/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.2.29201.188"; Url="https://download.visualstudio.microsoft.com/download/pr/39a6df29-f34a-445f-a7dc-231e2f398d04/24d2a8ccba13e7c21eb6bd5112a9c0c8/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.2.29123.88"; Url="https://download.visualstudio.microsoft.com/download/pr/3f236a83-2106-415c-9cd5-b75adcf61296/ceb6d027ad4d61c2ad9ee2e86ef264b4/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.1.29102.190"; Url="https://download.visualstudio.microsoft.com/download/pr/b58a1451-f938-4d57-ac35-7e110bccda7b/c0c5e94bfa3242bf96f5b762ce593ca4/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.1.29025.244"; Url="https://download.visualstudio.microsoft.com/download/pr/e4687c7d-c894-42d5-b71c-7d6b04e6317d/e672f0dbbdb4ef81410f54b01c6f12c2/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.1.29020.237"; Url="https://download.visualstudio.microsoft.com/download/pr/6a66cdad-7a25-4754-8be8-64f80eeeb28f/eac18ac0e11d0c685ebbd62a1d054bfc/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.1.29009.5"; Url="https://download.visualstudio.microsoft.com/download/pr/a00fe459-f370-4afb-8bcc-195fabf5e256/deb85c172a21423335aa1e1a85104186/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.1.29001.49"; Url="https://download.visualstudio.microsoft.com/download/pr/ad26cf60-3a2c-442e-af7b-56dc497e7dfd/e6216e4577eb42a1cb967753cfc56d1f/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.1.28922.388"; Url="https://download.visualstudio.microsoft.com/download/pr/e32f79fd-c215-4b66-ac8d-08539d30be3f/9aa970fd716d7a233eb6de2d54eca3cc/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.1.28917.181"; Url="https://download.visualstudio.microsoft.com/download/pr/3121e897-4582-40a5-a864-8a07488f8cf5/3e7dc9d529cff031d619b9ab42f4743d/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.916"; Url="https://download.visualstudio.microsoft.com/download/pr/0af00169-b3da-4369-a810-69b1c655d105/a610564bf5e214bc49c6a58e93c7a24d0ce49b1ffaec5fa957e2c8101f368ae2/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.902"; Url="https://download.visualstudio.microsoft.com/download/pr/eaea8234-3714-4eb4-8141-ee8a849e660a/54d1f5f1794ae343802ac627881dec34833366d2b162af7b08ed4b78c98ea4a2/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.868"; Url="https://download.visualstudio.microsoft.com/download/pr/7d4bdacd-6850-4fca-a533-f6c6e71fb6df/b4206df3ed9885a9352123e93644f8b682f58bb431c635f86ec29dedde0efee8/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.846"; Url="https://download.visualstudio.microsoft.com/download/pr/fe9261d0-a86c-47f0-8797-6d2eee60c960/eb17f2638edd9fa3b0ea5e270a670c3a5f8fe543a60bab01431e874d6553f174/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.826"; Url="https://download.visualstudio.microsoft.com/download/pr/2f673e29-c840-4898-9331-889675e71f6e/49c6af271f254553c70860fd9876ff188fe219f2df96156091f7e4bab77d873f/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.806"; Url="https://download.visualstudio.microsoft.com/download/pr/9c25c0a6-ae72-4043-8f03-c9fd6dffc6e6/fb9ade53e6a5bf5ffce278fa38f33eace8a9068ca6aab79a3a0dec4411625e86/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.791"; Url="https://download.visualstudio.microsoft.com/download/pr/372c3f71-a2ec-4bea-b821-e84f03352d18/17a03a09556e19e5db57f4db419a17cdf9de77df9877836b23b5064422006697/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.753"; Url="https://download.visualstudio.microsoft.com/download/pr/87c1df97-7a49-4c95-a6e8-34ce8ab23bfb/bfcf594e9bbf2e9c0c8a2a7c8085f7bafd17e03c4cfb71ab418ce747495ab83b/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.735"; Url="https://download.visualstudio.microsoft.com/download/pr/7e18cbea-d902-48bd-99d9-a7d730c2b07c/0f6550229e452704151a3b29c3030baef4c5406e1448790bf9ba5832e4ed94a5/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.718"; Url="https://download.visualstudio.microsoft.com/download/pr/75d83464-a47a-4bec-9efc-4acc69cc979d/902fc13ea7e27d3a9fe14d60a14b68d760d93bfacf184c1ab585936ab5b56880/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.697"; Url="https://download.visualstudio.microsoft.com/download/pr/0586016c-aae3-4200-9c8a-88c313a87c8e/d571c3b268abb91598c0e5d242c6156bfdbbae6fdd1461c4a2589d467837c621/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.653"; Url="https://download.visualstudio.microsoft.com/download/pr/5bac4312-9840-4ac1-b6b6-dae59c3eb3b2/cc06856ce1cd3c682b1325ba91e68541ca452cfc0b7f53d83b53d22b20149d2e/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.631"; Url="https://download.visualstudio.microsoft.com/download/pr/f98a52f5-ca48-4f55-bde4-7ed02b368e01/f638a1597261645fc930e2f5b4ccff2def2058e24685eee94916ac2656dc800d/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.598"; Url="https://download.visualstudio.microsoft.com/download/pr/2c4e70e5-e729-4d35-a976-c450932d5aa2/e11e235bb0d5449c796b20278c210482ddf585a5f1b3f9454c3c7e15556be25a/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.584"; Url="https://download.visualstudio.microsoft.com/download/pr/8857a84a-c45a-4981-8454-1790f21f2b59/cb1c6e68188848a03f1a875d6c0bb7b51f6d61620af8ff71a9ae2307453d4a6c/vs_BuildTools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.571"; Url="https://download.visualstudio.microsoft.com/download/pr/4a5e5b5b-343c-438b-854c-3541df0e83ad/371a18d5a7cef339b493b111ff8d8ea3/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.540"; Url="https://download.visualstudio.microsoft.com/download/pr/9735057b-f765-416e-8318-7ff1aa60df22/1739e68a58c7aa843a8a8ecb2edc3a21/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.514"; Url="https://download.visualstudio.microsoft.com/download/pr/c8c868de-5584-4a05-ad9e-07ac0ad08c70/a065f8079fe22a310414911a834d5687/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.452"; Url="https://download.visualstudio.microsoft.com/download/pr/804e3b16-6458-4086-9412-88c3d8f990df/bec5df58239bec09bae881fe3d47e7f1/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.352"; Url="https://download.visualstudio.microsoft.com/download/pr/8e5c53a1-8685-4c3f-8e06-084419fe4734/5aa75ba181f03e686ae2545f3f288e74/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.202"; Url="https://download.visualstudio.microsoft.com/download/pr/3eab8ec9-8b46-4442-8ef6-d86db67df2d0/a20f8b015bc1d9f9317fa850b2d85b1f/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28803.156"; Url="https://download.visualstudio.microsoft.com/download/pr/f6595fb7-8d1c-4a1d-9351-76438b0b1f33/e366280d0e6f8b6ee31985ff1a48b3ec/vs_buildtools.exe" }),
    (New-Object PSObject -Property @{ Version="16.0.28729.10"; Url="https://download.visualstudio.microsoft.com/download/pr/e1791fdb-bc8c-491c-a01a-a66ca93e2ccc/c8b42c363e2885c1ae2d8bb5634a9540/vs_buildtools.exe" })
)

$download_path = "D:/efs/download"
$full_install_root = "D:/efs/full"
$archives = "D:/efs/archives"

function Download {
    Param (
        [string] $version,
        [string] $url
    )

    $versionPath = "$download_path/$version"
    $filepath = "$versionPath/installer.exe"

    if (!(Test-Path -Path $filepath)) {
        New-Item -ItemType Directory $versionPath
        Invoke-WebRequest -Uri $url -OutFile $filepath
    }
}

function Install {
    Param (
        [string] $version
    )

    $installer = "$download_path/$version/installer.exe"

    New-Item -ItemType Directory -Force "$full_install_root/$version"
    Start-Process -Wait -FilePath "$installer" -ArgumentList @("--quiet", "--installPath", "$full_install_root/$version", "--add", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "--add", "Microsoft.VisualStudio.Component.VC.Tools.ARM64", "--add", "Microsoft.VisualStudio.Component.VC.Tools.ARM")
}

function Uninstall {
    Param (
        [string] $version
    )

    # $installer = "$download_path/$version/installer.exe"

    # this doesn't work unfortunately
    # Start-Process -Wait -FilePath "$installer" -ArgumentList @("uninstall", "--wait", "--quiet", "--installPath", "$full_install_root/$version",  "--remove", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "--remove", "Microsoft.VisualStudio.Component.VC.Tools.ARM64", "--remove", "Microsoft.VisualStudio.Component.VC.Tools.ARM")

    Remove-Item -Recurse -Force "$full_install_root/$version"
}


function ZipVC {
    Param (
        [string] $version,
        [string] $compilerVersion,
        [string] $productVersion
    )

    New-Item -ItemType Directory -Force "$archives"
    Compress-Archive -DestinationPath "$archives/$compilerVersion-$productVersion.zip" -Path "$full_install_root/$version/VC/Tools/MSVC/$compilerVersion"
}

New-Item -ItemType Directory -Force "$full_install_root"

foreach ($version in $versions)
{
    $installVersion = $version.Version

    Write-Host "Installer version: $installVersion"
    Download -version $installVersion -url $version.Url
    Install -version $installVersion

    $dir = "$full_install_root/$installVersion/VC/Tools/MSVC"
    Get-ChildItem $dir | Foreach-Object {
        $compilerVersion = $_.Name
        Write-Host "Compiler directory version: $compilerVersion"

        # $compilerExeFileVersion = (Get-Item "$dir/$compilerVersion/bin/Hostx64/x64/cl.exe").VersionInfo.FileVersionRaw
        $compilerExeProductVersion = (Get-Item "$dir/$compilerVersion/bin/Hostx64/x64/cl.exe").VersionInfo.ProductVersionRaw
        Write-Host "Compiler exe version: $compilerExeProductVersion"

        ZipVC -version $version.Version -compilerVersion $compilerVersion -productVersion $compilerExeProductVersion
    }

    Uninstall -version $version.Version
}
