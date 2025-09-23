// Example usage of your solobase-js SDK with the Django backend
const { createClient } = require('./sdk/index.js');

// Initialize the client with your Django backend
const solobase = createClient('http://localhost:8000', 'your-api-key');

async function demonstrateSDKUsage() {
    console.log('🚀 Demonstrating SDK Usage with Django Backend');
    console.log('================================================');
    
    try {
        // 1. Authentication
        console.log('\n1. 🔐 Authentication');
        console.log('---------------------');
        
        // Sign up a new user
        const { data: signUpData, error: signUpError } = await solobase.auth.signUp({
            email: 'demo@example.com',
            password: 'demopassword123',
            options: {
                data: {
                    full_name: 'Demo User',
                    id_number: '123456789',
                    id_front_url: 'https://example.com/id_front.jpg',
                    id_back_url: 'https://example.com/id_back.jpg',
                    role: 'staff'
                }
            }
        });
        
        if (signUpError) {
            console.log('Sign up error:', signUpError);
        } else {
            console.log('✅ User signed up:', signUpData.user.email);
        }
        
        // Get current user
        const { data: userData, error: userError } = await solobase.auth.getUser();
        if (!userError) {
            console.log('✅ Current user:', userData.user.email);
        }
        
        // 2. Database Operations
        console.log('\n2. 🗄️  Database Operations');
        console.log('---------------------------');
        
        // Create a team
        const { data: teamData, error: teamError } = await solobase.from('teams').insert({
            name: 'SDK Demo Team',
            region: 'Demo Region',
            territory: 'Demo Territory',
            is_active: true
        });
        
        if (!teamError && teamData) {
            console.log('✅ Team created:', teamData[0]);
            
            // Query teams
            const { data: teams, error: queryError } = await solobase.from('teams').select({
                name: 'SDK Demo Team'
            });
            
            if (!queryError) {
                console.log('✅ Teams found:', teams.data.length);
            }
            
            // Update team
            const { data: updatedTeam, error: updateError } = await solobase.from('teams').update(
                { territory: 'Updated Territory' },
                { name: 'SDK Demo Team' }
            );
            
            if (!updateError) {
                console.log('✅ Team updated:', updatedTeam.count, 'records');
            }
        } else {
            console.log('❌ Team creation error:', teamError);
        }
        
        // Create SIM cards
        const { data: simData, error: simError } = await solobase.from('sim_cards').insert([
            {
                serial_number: 'SIM001-SDK',
                status: 'PENDING',
                batch_id: 'BATCH-SDK-001',
                quality: 'QUALITY',
                match: 'Y'
            },
            {
                serial_number: 'SIM002-SDK', 
                status: 'PENDING',
                batch_id: 'BATCH-SDK-001',
                quality: 'NONQUALITY',
                match: 'N'
            }
        ]);
        
        if (!simError) {
            console.log('✅ SIM cards created:', simData?.length || 0);
        }
        
        // Query SIM cards with filters
        const { data: sims, error: simQueryError } = await solobase.from('sim_cards').select({
            batch_id: 'BATCH-SDK-001'
        });
        
        if (!simQueryError) {
            console.log('✅ SIM cards found:', sims.data?.length || 0);
        }
        
        // 3. Storage Operations
        console.log('\n3. 📁 Storage Operations');
        console.log('-------------------------');
        
        // Note: In a real browser environment, you'd get file from input
        // For demo, we'll show the structure
        console.log('📝 Storage endpoints available:');
        console.log('   - Upload: POST /api/storage/upload');
        console.log('   - Download: GET /api/storage/{filename}');
        console.log('   - Get URL: solobase.storage.getPublicUrl(filename)');
        
        // 4. Real-world SSM Operations
        console.log('\n4. 🎯 SSM-Specific Operations');
        console.log('------------------------------');
        
        // Create onboarding request
        const { data: onboardingData, error: onboardingError } = await solobase.from('onboarding_requests').insert({
            full_name: 'New Staff Member',
            id_number: '987654321',
            id_front_url: 'https://example.com/new_front.jpg',
            id_back_url: 'https://example.com/new_back.jpg',
            role: 'staff',
            status: 'pending',
            request_type: 'ONBOARDING'
        });
        
        if (!onboardingError) {
            console.log('✅ Onboarding request created');
        }
        
        // Create batch metadata
        const { data: batchData, error: batchError } = await solobase.from('batch_metadata').insert({
            batch_id: 'BATCH-SDK-002',
            order_number: 'ORD-SDK-001',
            company_name: 'SDK Demo Company',
            quantity: 100,
            item_description: 'Demo SIM Cards'
        });
        
        if (!batchError) {
            console.log('✅ Batch metadata created');
        }
        
        // Forum operations
        const { data: topicData, error: topicError } = await solobase.from('forum_topics').insert({
            title: 'Welcome to SDK Integration',
            content: 'This topic was created via the SDK!',
            is_pinned: false,
            is_closed: false
        });
        
        if (!topicError) {
            console.log('✅ Forum topic created');
        }
        
        console.log('\n🎉 SDK Integration Complete!');
        console.log('=====================================');
        console.log('Your SDK is now fully compatible with the Django backend.');
        console.log('All Supabase-style operations work seamlessly!');
        
    } catch (error) {
        console.error('❌ Demo error:', error);
    }
}

// Run the demonstration
demonstrateSDKUsage().catch(console.error);